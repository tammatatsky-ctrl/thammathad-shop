"""Service layer — ตรรกะข้ามโมดูลที่ "ไม่ใช่หน้าที่ของ view ใด view เดียว"
view ทำหน้าที่เรียกใช้ service เท่านั้น ไม่ใส่ business logic ไว้ใน view เอง.

สถาปัตยกรรม (map ทั้ง module):
- Cart        : ตะกร้าสินค้าใน session (cart / checkout / ปุ่มใส่ตะกร้า ใช้ object เดียวกัน)
- ThaiCalendar: คำทักทาย + วันที่แบบพุทธศักราช + วันหยุดราชการไทย (Google ICS)
                 + next_business_day() สำหรับ ETA หน้าสั่งซื้อสำเร็จ
- ExchangeRate: อัตราแลกเปลี่ยน THB→USD จาก external API (โชว์การ "เรียกใช้" API)
- GeoIP       : ตำแหน่งโดยประมาณจาก IP (ipwho.is — keyless) เป็นคำใบ้ระดับประเทศ
- Translate   : แปล EN↔TH (MyMemory — keyless) ช่วยฟอร์มสินค้าเมื่อไม่มี Gemini key
- Catalog     : แคชหมวดหมู่สินค้า TTL 60 วิ + invalidation ผ่าน signal (models.py)
- RateLimit   : จำกัดอัตราเรียก endpoint ต่อ IP ด้วย cache (slip OCR)
- LoginThrottle: กัน brute force หน้า login (3 ชั้น: IP → IP+ชื่อ → ต่อบัญชี)
- PromptPay   : QR พร้อมเพย์สำหรับหน้าสั่งซื้อสำเร็จ
- SlipOK      : OCR ตรวจสลิปโอนเงิน (API key ว่าง = ฟีเจอร์ถูกซ่อน + view ซ่อน UI)
- GeminiAI    : ข้อความช่วยเขียนคำอธิบายสินค้า (Google Gemini REST API)
- Validators  : ตรวจ/แปลงข้อมูลผู้ใช้ที่ใช้ร่วมกันหลายหน้า
- OrderStatusService: บันไดสถานะขั้นเดียว (pending → paid → shipped → delivered)
                      กติกาใบงาน: ห้ามข้ามขั้น/ห้ามถอยหลัง, paid เป็นขั้นอัตโนมัติ
- PaymentService: จุดรับเงินจุดเดียว — ทุกช่องทางจ่ายเงินต้องเรียกที่นี้ แล้ว
                  ระบบดูเองว่า "ครบยอดหรือยัง" → ขยับสถานะ paid อัตโนมัติ
- Audit        : บันทึก "ใครทำอะไร" (ActivityLog) — log พังห้ามทำให้งานหลักพัง

ทุก service ใช้ staticmethod/classmethod (ไม่ต้องสร้าง instance) —
รวมโค้ดที่เกี่ยวข้องเข้าด้วยกันและ test ได้อิสระจาก view.
"""
import base64
import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

from .models import Order, Payment, Product


class Catalog:
    """ตัวช่วยหน้าร้าน-แคตตาล็อก: เครื่องมือที่เรียกซ้ำข้ามหน้า แล้วควรแคช
    (เช่น หมวดหมู่สินค้า) — ลด SELECT DISTINCT ซ้ำต่อ request.
    แคช locmem TTL 60 วิ — ข้อมูลเล็ก, ค่าเก่าชั่วครู่รับได้ หมวดใหม่จะปรากฏใน ~1 นาที."""

    CATS_TTL = 60

    @staticmethod
    def _cats_key(only_listed):
        """ชื่อ cache key ของ variant หมวดหมู่ — จุดเดียวที่รู้ชื่อ key (categories/invalidate ใช้ร่วมกัน)."""
        return 'catalog:cats:listed' if only_listed else 'catalog:cats:all'

    @staticmethod
    def categories(only_listed=True):
        """หมวดหมู่สินค้าสำหรับ filter (เรียง A-Z) — แคชตาม variant
        (เฉพาะสินค้าที่แสดง / ทุกตัว) กัน query ซ้ำ.

        Args:
            only_listed: True = หมวดของสินค้า is_active เท่านั้น (หน้าร้าน),
                         False = ทุกหมวดรวมของที่ซ่อน (ฟอร์มจัดการสินค้า)

        Returns:
            list[str] หมวดหมู่เรียง A-Z
        """
        key = Catalog._cats_key(only_listed)
        val = cache.get(key)
        if val is None:
            qs = Product.objects.listed() if only_listed else Product.objects.all()
            val = list(qs.category_choices())
            cache.set(key, val, Catalog.CATS_TTL)
        return val

    @staticmethod
    def invalidate():
        """ล้างแคชหมวดหมู่ทั้งสอง variant — ให้หมวดใหม่/ที่หายไปสะท้อนทันทีโดยไม่ต้องรอ TTL.

        เรียกอัตโนมัติจาก signal post_save/post_delete ของ Product (myapp/models.py)
        จึงครอบทุกทางที่สินค้าเปลี่ยน: หน้าจัดการสินค้า, Django admin, shell.
        """
        cache.delete_many([Catalog._cats_key(True), Catalog._cats_key(False)])


class RateLimit:
    """จำกัดอัตราการเรียก endpoint ต่อผู้เรียก (IP) ด้วย Django cache — ไม่พึ่ง package ภายนอก.

    ใช้กับ endpoint สาธารณะที่มีต้นทุนจริง เช่นอัปโหลดสลิป (เรียก SlipOK ภายนอกทุกครั้ง)
    หรือขอ token (กัน brute force รหัสผ่านผ่าน API). เป็น fixed-window counter:
    เปิดหน้าต่างด้วย cache.add ครั้งแรก แล้วนับด้วย cache.incr จนครบโควตา.

    หมายเหตุ:
    - ใช้ cache ตัวเดียวกับระบบ (locmem) → นับ "ต่อ process"; production หลาย worker
      อาจนับแยกกัน (ยอมรับได้ในระดับ demo — ย้ายเป็น Redis ได้โดยไม่แก้โค้ดนี้)
    - นับจาก REMOTE_ADDR ตรง ๆ ไม่ใช้ X-Forwarded-For (header ปลอมได้ — กัน bypass)
    """

    @staticmethod
    def allow(scope, ident, limit=10, window=60):
        """นับคำขอนี้เข้าโควตา — คืน True ถ้ายังผ่าน, False ถ้าเกิน (ควรตอบ 429).

        Args:
            scope: ชื่อกลุ่มการจำกัด (เช่น 'slip')
            ident: ตัวระบุผู้เรียก (ปกติ REMOTE_ADDR)
            limit: จำนวนครั้งสูงสุดต่อหน้าต่าง
            window: ขนาดหน้าต่างเวลา (วินาที)

        Returns:
            bool: True = ผ่าน (นับแล้ว), False = เกินโควตา
        """
        key = f'ratelimit:{scope}:{ident}'
        if cache.add(key, 1, window):
            return True
        try:
            return cache.incr(key) <= limit
        except ValueError:
            # key หมดอายุระหว่างทาง (race) → เริ่มหน้าต่างใหม่
            cache.add(key, 1, window)
            return True


class LoginThrottle:
    """กัน brute force หน้า login (staff + ลูกค้า) — ต่อยอดจาก RateLimit.

    เหตุผลที่แยกจาก RateLimit: หน้า login ต่างจาก endpoint ทั่วไปตรงที่
    "ห้ามบอกว่ารหัสผิด" (user enumeration / oracle) และการโดนล็อกทั้ง IP
    ระยะยาวทำให้ผู้ใช้จริงจากห้องเดียวกันโดนผลพลัพธ์ — จึงไล่ 3 ชั้น:

      1. ต่อ IP          : โหลดหนักเกิน (DoS / distributed brute force)
      2. ต่อ IP+username : เดาเป็นพิเศษรายบัญชี (credential stuffing)
      3. แตะละบัญชีให้  : ตัวสุดท้ายกัน account takeover แบบเจาะชื่อเดียว

    ทั้ง 3 ชั้นใช้ counter แบบเดียวกับ RateLimit (locmem fixed-window)
    → ถ้าวันหนึ่งย้ายไป Redis ก็เปลี่ยนที่ service เดียว

    บันไดการตอบ: ทุกชั้นคืน False → 429 + ข้อความเดียวกันหมด (ไม่บอกว่าชั้นไหนโดน)
    """

    # โควตา/หน้าต่างต่อชั้น (วินาที) — เผื่อผิดพลาดจริงไว้ แต่ไม่ให้ brute force ได้
    IP_LIMIT, IP_WINDOW = 20, 300        # ต่อ IP: 20 ครั้ง / 5 นาที
    PAIR_LIMIT, PAIR_WINDOW = 8, 300     # ต่อ IP+ชื่อ: 8 ครั้ง / 5 นาที
    USER_LIMIT, USER_WINDOW = 5, 900     # ต่อบัญชี: 5 ครั้ง / 15 นาที

    # ข้อความเดียวสำหรับทุกกรณีที่โดนจำกัด — ตั้งใจไม่บอกว่า "ชั้นไหนโดน"
    # เพื่อไม่ให้ผู้โจมตีเดาเงื่อนไขว่าตัวเองถูกล็อกที่ระดับ IP หรือระดับบัญชี
    MESSAGE = 'พยายามเข้าสู่ระบบบ่อยเกินไป — กรุณารอสักครู่แล้วลองใหม่'

    @classmethod
    def check(cls, ip, username):
        """เช็คว่าการลองครั้งนี้ยังอยู่ในโควตาหรือไม่ (ก่อน authenticate).

        เช็ค 3 ชั้น: IP → IP+ชื่อ → ตัวนับความล้มเหลวของบัญชีนั้น

        Args:
            ip: REMOTE_ADDR ของผู้เรียก
            username: ชื่อผู้ใช้ที่กำลังลอง (normalize เป็นตัวพิมพ์เล็ก)

        Returns:
            bool: True = ยังลองได้, False = โดนจำกัด (ควรตอบ 429)
        """
        uname = (username or '').strip().lower() or '-'
        # short-circuit: โดนชั้นไหนก็จบ ไม่เพิ่มตัวนับของชั้นถัดไป
        if not RateLimit.allow('login-ip', ip, cls.IP_LIMIT, cls.IP_WINDOW):
            return False
        if not RateLimit.allow('login-pair', f'{ip}|{uname}', cls.PAIR_LIMIT, cls.PAIR_WINDOW):
            return False
        # ชั้นบัญชี: ดูอย่างเดียว (อ่าน ไม่นับ) — การนับอยู่ฝั่ง fail()
        return cache.get(f'ratelimit:login-fail-user:{uname}', 0) < cls.USER_LIMIT

    @classmethod
    def fail(cls, username):
        """บันคิดความล้มเหลวของบัญชี 1 ครั้ง.

        หมายเหตุเรื่องความปลอดภัย: ชั้น "ต่อบัญชี" นับจาก *ความล้มเหลว* ไม่ใช่จาก
        จำนวนครั้งที่กด เพราะ (ก) ถ้านับทุกครั้งที่กด ผู้ใช้ที่พิมพ์ถูกแต่กดซ้ำจะโดนล็อกเอง
        (self-DoS) และ (ข) ผู้โจมตีที่เดาชื่อบัญชีไม่มีอยู่จริงจะไม่ถูกนับเลย —
        ซึ่งถูกต้อง เพราะเป้าหมายของ account takeover คือบัญชีที่มีอยู่จริง
        (ชั้น IP ยังคุมการเดาชื่อปลอมนั่นอยู่)

        Args:
            username: ชื่อผู้ใช้ที่ล้มเหลว
        """
        uname = (username or '').strip().lower() or '-'
        RateLimit.allow('login-fail-user', uname, cls.USER_LIMIT, cls.USER_WINDOW)

    @classmethod
    def success(cls, username):
        """ล้างตัวนับความล้มเหลวของบัญชีหลังเข้าสำเร็จ.

        ไม่ล้างชั้น IP/IP+ชื่อโดยเจตนา: ถ้าล้าง ผู้โจมตีที่เพิ่งได้บัญชีมาหนึ่งบัญชี
        จะเคลียร์ตัวนับทั้งหมดของตัวเองได้ทันที = ทำให้กลไกกัน brute force ทิ้ง

        Args:
            username: ชื่อผู้ใช้ที่เข้าสำเร็จ
        """
        uname = (username or '').strip().lower() or '-'
        cache.delete(f'ratelimit:login-fail-user:{uname}')


class Audit:
    """บันทึกการกระทำของเจ้าหน้าที่ — ตอบคำถาม "ใครทำอะไร เมื่อไหร่"

    หลักการที่ยึด (สำคัญกว่าตัวฟังก์ชัน):
    1. **การ log ต้องไม่ทำให้งานหลักพัง** — ถ้าเขียน ActivityLog ล้ม
       (เช่น ตารางยังไม่ถูก migrate) ต้องยังทำงานต่อ ไม่ใช่ทำให้
       "กดเติมสต็อกไม่ได้เพราะ log error"
    2. **อย่าเก็บข้อมูลส่วนตัวเกินจำเป็น** — เก็บเฉพาะฟิลด์ที่ต้องรู้ว่า
       เปลี่ยนอะไร (เช่น stock/price/status) ไม่ dump ทั้งออบเจกต์ลง JSON
    3. **คงชื่อผู้ทำเป็นข้อความด้วย** เพราะ FK เป็น SET_NULL — ถ้าภายหลัง
       ลบบัญชี ประวัติต้องยังบอกได้ว่าใครเป็นคนทำ
    4. **ปิดได้** — `settings.ACTIVITY_LOG_ENABLED = False` จะทำให้เป็น
       no-op ทันที (ตอนเทสต์เร็ว ๆ หรือถ้าไม่ต้องการเก็บ)

    ตัวอย่างการใช้:
        Audit.record(request.user, 'stock',
                     summary=f'ปรับสต็อกสินค้า #{p.id} +5',
                     target=p, before={'stock': 10}, after={'stock': 15},
                     request=request)
    """

    #: ฟิลด์ที่อนุญาตให้เก็บใน before/after (กันการ dump ข้อมูลส่วนตัว/ใหญ่เกิน)
    SAFE_FIELDS = {
        'stock', 'price', 'status', 'salary', 'is_active', 'department',
        'category', 'name', 'total', 'quantity', 'payment_method', 'hire_date',
    }

    @classmethod
    def record(cls, actor=None, action='', summary='', target=None,
               before=None, after=None, request=None):
        """เขียนบันทึก 1 รายการ (ไม่เคยทำให้ธุรกรรมหลักล้ม)

        Args:
            actor: User ที่กระทำ (None = ระบบ/ไม่มีผู้ใช้)
            action: หนึ่งใน ActivityLog.ACTION_CHOICES
            summary: คำอธิบายสั้น ๆ ที่คนอ่านรู้เรื่อง (max 300)
            target: ออบเจกต์ที่ถูกแก้ (ใช้เลข id + label)
            before: dict ค่าเดิม (กรองเฉพาะ SAFE_FIELDS)
            after: dict ค่าใหม่ (กรองเฉพาะ SAFE_FIELDS)
            request: HttpRequest (ใช้ดึง IP เท่านั้น)

        Returns:
            ActivityLog | None — instance ที่บันทึกได้, หรือ None ถ้าไม่ได้เขียน
        """
        if not getattr(settings, 'ACTIVITY_LOG_ENABLED', True):
            return None

        try:
            from .models import ActivityLog

            target_type = target_label = target_id = ''
            if target is not None:
                target_type = target.__class__.__name__.lower()
                target_id = str(getattr(target, 'pk', ''))
                target_label = str(target)[:150]

            return ActivityLog.objects.create(
                actor=actor if getattr(actor, 'is_authenticated', False) else None,
                actor_name=(actor.get_username() if getattr(actor, 'is_authenticated', False)
                            else '')[:150],
                action=action,
                summary=(summary or '')[:300],
                target_type=target_type,
                target_id=target_id,
                target_label=target_label,
                before=cls._clean(before),
                after=cls._clean(after),
                ip=cls._client_ip(request),
            )
        except Exception:
            # ข้อ 1: log พังห้ามไปลากงานหลักพังตาม — แจ้งเตือนทาง log แล้วจบ
            import logging
            logging.getLogger(__name__).warning(
                'บันทึก ActivityLog ไม่สำเร็จ (action=%s) — ทำงานต่อ', action,
                exc_info=True)
            return None

    @classmethod
    def _clean(cls, data):
        """กรอง dict ให้เหลือเฉพาะ SAFE_FIELDS + ทำค่าให้เป็น string/ตัวเลข

        Args:
            data: dict ค่าก่อน/หลัง (อาจเป็น None)

        Returns:
            dict | None
        """
        if not data:
            return None
        out = {}
        for key, value in data.items():
            if key not in cls.SAFE_FIELDS:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[key] = value
            else:
                out[key] = str(value)[:60]
        return out or None

    @staticmethod
    def _client_ip(request):
        """ดึง IP ของผู้ทำ

        อ่าน REMOTE_ADDR ตรง ๆ ไม่ใช้ X-Forwarded-For (header ปลอมได้ —
        การบันทึก IP เพื่อตรวจสอบ ต้องไม่เชื่อค่าที่ผู้ใช้ควบคุมได้)
        """
        if request is None:
            return None
        ip = request.META.get('REMOTE_ADDR') or ''
        return ip or None

    @classmethod
    def diff(cls, obj, fields, before):
        """คืน dict ของ 'ค่าที่เปลี่ยนจริง' เทียบกับ before — ลดข้อมูลเปลือกใน log

        ใช้ใน view แบบ: `after = Audit.diff(emp, ['salary','department'], before=old)`

        Args:
            obj: ออบเจกต์หลังแก้ (หรือ instance ปัจจุบัน)
            fields: รายการฟิลด์ที่อยากติดตาม
            before: dict ค่าเดิมที่ snapshot ไว้ก่อนแก้

        Returns:
            dict — เฉพาะฟิลด์ที่ค่าเปลี่ยนจริง
        """
        after = {}
        for f in fields:
            new = getattr(obj, f, None)
            old = (before or {}).get(f)
            if str(new) != str(old):
                after[f] = new
        return after


class ThaiCalendar:
    """จัดรูปแบบวันที่/คำทักไทย (Buddhist Era)"""

    MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
              'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    DAYS = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']

    @classmethod
    def greeting(cls, now=None):
        """คำทักทายตามช่วงเวลาของวัน (แบ่ง 5 กลุ่มเวลา).

        Args:
            now: เวลาอ้างอิง (default = เวลาท้องถิ่นผ่าน timezone.localtime)

        Returns:
            str เช่น "สวัสดีตอนเช้า", "สวัสดีตอนกลางคืน"
        """
        now = now or timezone.localtime()
        if 5 <= now.hour < 12:
            return 'สวัสดีตอนเช้า'
        if 12 <= now.hour < 16:
            return 'สวัสดีตอนบ่าย'
        if 16 <= now.hour < 21:
            return 'สวัสดีตอนเย็น'
        return 'สวัสดีตอนกลางคืน'

    @classmethod
    def full_date(cls, now=None):
        """วันที่แบบไทยเต็มรูปแบบ (วัน — เดือน — พุทธศักราช).

        Args:
            now: เวลาอ้างอิง (default = เวลาท้องถิ่น)

        Returns:
            str เช่น "วันอังคารที่ 25 สิงหาคม 2569" (ค.ศ. + 543 = พ.ศ.)
        """
        now = now or timezone.localtime()
        return (
            f"วัน{cls.DAYS[now.weekday()]}ที่ {now.day} "
            f"{cls.MONTHS[now.month - 1]} {now.year + 543}"
        )

    @classmethod
    def format(cls, dt=None):
        """จัดรูปแบบวันที่แบบไทย พ.ศ. (เช่น "8 กันยายน 2569").

        รับได้ทั้ง datetime (aware/naive) และ date ธรรมดา — `next_business_day()`
        คืน date จึงต้องเรียกผ่านทางนี้ได้ (date ไม่มี utcoffset).
        """
        if not dt:
            return ""
        if isinstance(dt, datetime) and timezone.is_aware(dt):
            dt = timezone.localtime(dt)
        return f"{dt.day} {cls.MONTHS[dt.month - 1]} {dt.year + 543}"

    # ----- วันหยุดนักขัตฤกษ์ไทย (Google Calendar ICS สาธารณะ — ฟรี ไม่ต้องใช้ key) -----

    HOLIDAY_ICS_URL = ('https://calendar.google.com/calendar/ical/'
                       'th.th%23holiday%40group.v.calendar.google.com/public/basic.ics')
    HOLIDAYS_TTL = 24 * 60 * 60       # สำเร็จ → แคช 1 วัน
    HOLIDAYS_FAIL_TTL = 10 * 60       # ล่ม → แคชสั้น ๆ 10 นาที (ค่อยลองใหม่ ไม่ทิ้งทั้งวัน)
    # Google ICS ของไทยปน "วัน observance" ที่ไม่ใช่วันหยุดราชการ (ทดสอบจริง 2026:
    # วาเลนไทน์, ตรุษจีน ×3, คริสต์มาสอีฟ, คริสต์มาส) → กรองออกเพื่อไม่ให้ ETA ข้ามวันทำการผิด
    HOLIDAY_SKIP_KEYWORDS = ('ตรุษจีน', 'วาเลนไทน์', 'คริสต์มาส', 'ฮาโลวีน', 'อีสเตอร์', 'ขอบคุณพระเจ้า')

    @staticmethod
    def parse_ics(text):
        """แกะไฟล์ ICS → {date: ชื่อวันหยุด} (ฟังก์ชันบริสุทธิ์ — เทสต์ได้โดยไม่ต่อเน็ต).

        รองรับ: `DTSTART;VALUE=DATE:YYYYMMDD`, `SUMMARY:ชื่อ` (มีภาษาไทย),
        line folding (บรรทัดต่อขึ้นต้นด้วยช่องว่าง) และ unescape `\\,` `\\;` `\\\\` ตามสเปก ICS.

        Args:
            text: เนื้อหา ICS ทั้งไฟล์

        Returns:
            dict[date, str]: วันหยุด → ชื่อ (ค่าว่างถ้าแกะไม่ได้เลย)
        """
        unfolded = re.sub(r'\r?\n[ \t]', '', text)  # คลาย line folding
        out = {}
        start_raw = summary = None
        for line in unfolded.splitlines():
            if line.startswith('DTSTART'):
                m = re.search(r'(\d{8})', line)
                start_raw = m.group(1) if m else None
            elif line.startswith('SUMMARY'):
                summary = line.split(':', 1)[1].strip() if ':' in line else ''
            elif line.startswith('END:VEVENT'):
                if start_raw and summary:
                    try:
                        d = date(int(start_raw[:4]), int(start_raw[4:6]), int(start_raw[6:8]))
                    except ValueError:
                        pass
                    else:
                        out[d] = (summary.replace('\\,', ',').replace('\\;', ';')
                                  .replace('\\\\', '\\'))
                start_raw = summary = None
        return out

    @classmethod
    def holidays(cls, year=None):
        """วันหยุดนักขัตฤกษ์ของปี (cache 24 ชม.) — คืน {} ถ้าดึงไม่ได้.

        สัญญาแบบเดียวกับ ExchangeRate: ไม่ raise, หน้าเว็บไม่พังถ้า API ล่ม
        (template จะไม่แสดงบรรทัด ETA เลย).

        Args:
            year: ปี ค.ศ. (default = ปีปัจจุบัน)

        Returns:
            dict[date, str]
        """
        year = year or timezone.localdate().year
        key = f'thai-holidays:{year}'
        cached = cache.get(key)
        if cached is not None:
            return cached
        data = {}
        try:
            req = urllib.request.Request(cls.HOLIDAY_ICS_URL,
                                         headers={'User-Agent': 'thammathad-shop/1.0'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                parsed = cls.parse_ics(resp.read().decode('utf-8', 'replace'))
            data = {
                d: n for d, n in parsed.items()
                if d.year == year
                and not any(kw in n for kw in cls.HOLIDAY_SKIP_KEYWORDS)   # ตัด observance
            }
        except Exception:
            data = {}
        cache.set(key, data, cls.HOLIDAYS_TTL if data else cls.HOLIDAYS_FAIL_TTL)
        return data

    @classmethod
    def is_holiday(cls, d):
        """วันนี้เป็นวันหยุดนักขัตฤกษ์ไหม (เสาร์/อาทิตย์ไม่นับ — ดู next_business_day)."""
        return d in cls.holidays(d.year)

    @classmethod
    def next_business_day(cls, start=None, include_start=False):
        """วันทำการถัดไป — ข้ามเสาร์/อาทิตย์ + วันหยุดนักขัตฤกษ์ไทย.

        ใช้ประเมินกำหนดจัดส่งบนหน้าสำเร็จการสั่งซื้อ.

        Args:
            start: วันเริ่มนับ (default = วันนี้)
            include_start: True = นับวันเริ่มด้วยถ้าเป็นวันทำการ

        Returns:
            date: วันทำการถัดไป (เพดานกันลูป 60 วัน)
        """
        d = start or timezone.localdate()
        if not include_start:
            d += timedelta(days=1)
        for _ in range(60):
            if d.weekday() < 5 and not cls.is_holiday(d):
                return d
            d += timedelta(days=1)
        return d


class ExchangeRate:
    """อัตราแลกเปลี่ยน THB→USD จาก external API (open.er-api.com — ฟรี ไม่ต้องใช้ key)

    - Cache ในหน่วยความจำแบบ TTL 6 ชม. → เรียก API เฉพาะเมื่อหมดอายุ (ไม่ช้าหน้าเว็บ)
    - Timeout 5 วินาที + fallback: ถ้า API ล่ม/ออกเน็ตไม่ได้ ใช้ rate ล่าสุดที่เคยได้
    - คืน None ได้ (template จะซ่อนบรรทัด USD อัตโนมัติ — degrade อย่างสวยงาม)
    """

    API_URL = 'https://open.er-api.com/v6/latest/THB'
    TTL_SECONDS = 6 * 60 * 60
    _cache = {'rate': None, 'at': 0.0}

    @classmethod
    def usd_per_thb(cls):
        """อัตราเดียวสำหรับทั้งระบบ: 1 THB = กี่ USD.

        แคชในหน่วยความจำ TTL 6 ชม. + timeout 5 วิ → หน้าเว็บไม่อั้นรอ API.
        ถ้า API ล่มและไม่มีแคช → คืน None (template ซ่อนบรรทัด USD อัตโนมัติ).

        Returns:
            Decimal (เช่น 0.029...) หรือ None ถ้ายังไม่เคยได้ค่าเลย

        Raises:
            (ไม่ raise — ดัก Exception ทั้งหมดข้างใน แล้วคืน cache/None แทน)
        """
        now = time.monotonic()
        cached = cls._cache['rate']
        if cached is not None and now - cls._cache['at'] < cls.TTL_SECONDS:
            return cached
        try:
            req = urllib.request.Request(cls.API_URL, headers={'User-Agent': 'thammathad-shop/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            rate = Decimal(str(data['rates']['USD']))
            if rate > 0:
                cls._cache.update(rate=rate, at=now)
                return rate
        except Exception:
            pass
        return cached


class GeoIP:
    """ตำแหน่งคร่าว ๆ ของผู้เข้าชมจาก IP (ipwho.is — ฟรี ไม่ต้องใช้ key/สมัคร).

    ⚠️ ความแม่นยำที่ทดสอบจริง (ก.ย. 2026): ระดับ "ประเทศ" เชื่อถือได้ แต่ระดับจังหวัด
    ของไทยไม่แม่น — ยิง 5 ISP ไทย (AIS/True/CAT/3BB) ได้ region=Bangkok หมด →
    ใช้เป็น "คำใบ้" ระดับประเทศเท่านั้น **ห้าม prefill จังหวัด/ที่อยู่ผู้ใช้**.

    สัญญาบริการ (แบบเดียวกับ ExchangeRate): เรียกฝั่ง server, cache 24 ชม. ต่อ IP,
    timeout 4 วิ, ไม่ raise — IP ส่วนตัว/ล่ม → คืน None (template ซ่อนคำใบ้).
    """

    API_URL = 'https://ipwho.is/{ip}'
    TTL_SECONDS = 24 * 60 * 60
    _MISS = object()          # sentinel: "ถามแล้วแต่ไม่ได้" (กันยิงซ้ำถี่)
    _cache = {}               # ip -> (monotonic_at, payload | _MISS)

    @staticmethod
    def is_private(ip):
        """IP private/loopback/invalid ไหม — True = ไม่ต้องถาม API."""
        if not ip or ip == '::1':
            return True
        if ip.startswith('10.') or ip.startswith('127.') or ip.startswith('192.168.'):
            return True
        if ip.startswith('169.254.') or ip.startswith('0.'):
            return True
        if ip.startswith('172.'):
            try:
                return 16 <= int(ip.split('.')[1]) <= 31
            except (ValueError, IndexError):
                return True
        return False

    @classmethod
    def lookup(cls, ip):
        """ข้อมูลตำแหน่งโดยประมาณของ IP (cache 24 ชม.).

        Args:
            ip: IPv4/IPv6 ของผู้เรียก

        Returns:
            dict | None: {'country_code', 'country', 'region', 'city'} หรือ None
            (private / API ล่ม / ไม่สำเร็จ — ผู้เรียกต้องรองรับ None เสมอ)
        """
        if cls.is_private(ip):
            return None
        now = time.monotonic()
        hit = cls._cache.get(ip)
        if hit and now - hit[0] < cls.TTL_SECONDS:
            return None if hit[1] is cls._MISS else hit[1]

        payload = None
        try:
            req = urllib.request.Request(cls.API_URL.format(ip=ip),
                                         headers={'User-Agent': 'thammathad-shop/1.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('success'):
                payload = {
                    'country_code': (data.get('country_code') or '').upper(),
                    'country': data.get('country') or '',
                    'region': data.get('region') or '',
                    'city': data.get('city') or '',
                }
        except Exception:
            payload = None
        cls._cache[ip] = (now, payload if payload else cls._MISS)
        return payload

    @classmethod
    def visitor(cls, request):
        """ตำแหน่งโดยประมาณของผู้เรียก request นี้ (REMOTE_ADDR — ไม่ใช้ XFF ที่ปลอมได้)."""
        return cls.lookup(request.META.get('REMOTE_ADDR') or '')


class Translate:
    """แปลข้อความด้วย MyMemory (ฟรี ไม่ต้องใช้ key/สมัคร) — ตัวช่วยฟอร์มสินค้า EN→TH.

    กรณีใช้จริง: สตาฟวางสเปก/คำอธิบายอังกฤษจากผู้ผลิต → กดปุ่มแปลได้คำอธิบายไทย
    โดยไม่ต้องมี GEMINI_API_KEY (เป็นคู่หูของ GeminiAI ไม่ใช่ตัวแทน).

    สัญญาบริการ: cache 24 ชม. ต่อ (ข้อความ, คู่ภาษา) · timeout 5 วิ · ไม่ raise
    - จำกัด 500 ตัวอักษร/ครั้ง (โควตาผู้ใช้ไม่ระบุตัวตนของ MyMemory)
    - ตรวจข้อความเตือน "MYMEMORY WARNING" (โควตาหมด) → คืน '' ให้ view ตอบ error สุภาพ
    """

    API_URL = 'https://api.mymemory.translated.net/get'
    TTL_SECONDS = 24 * 60 * 60
    MAX_CHARS = 500

    @classmethod
    def text(cls, text, source='en', target='th'):
        """แปลข้อความ — คืน '' เมื่อใช้ไม่ได้ (ห้าม raise เด็ดขาด).

        Args:
            text: ข้อความต้นทาง (ตัดหัวท้าย; ยาวเกิน MAX_CHARS = ปฏิเสธ)
            source: รหัสภาษาต้นทาง (default 'en')
            target: รหัสภาษาปลายทาง (default 'th')

        Returns:
            str: ข้อความแปล หรือ '' ถ้าแปลไม่ได้/โควตาหมด/API ล่ม
        """
        text = (text or '').strip()
        if not text or len(text) > cls.MAX_CHARS or source == target:
            return ''
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]   # cache key (ไม่ใช่ความปลอดภัย)
        key = f'translate:{source}:{target}:{digest}'
        cached = cache.get(key)
        if cached is not None:
            return cached

        out = ''
        try:
            qs = urllib.parse.urlencode({'q': text, 'langpair': f'{source}|{target}'})
            req = urllib.request.Request(f'{cls.API_URL}?{qs}',
                                         headers={'User-Agent': 'thammathad-shop/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            translated = ((data.get('responseData') or {}).get('translatedText') or '').strip()
            try:
                status = int(data.get('responseStatus') or 200)
            except (TypeError, ValueError):
                status = 200
            if translated and status == 200 and 'MYMEMORY WARNING' not in translated.upper():
                out = translated
        except Exception:
            out = ''
        cache.set(key, out, cls.TTL_SECONDS)
        return out


class PromptPay:
    """QR พร้อมเพย์ — payload มาตรฐาน EMVCo จาก lib promptpay-qr + เรนเดอร์ PNG ด้วย qrcode
    คืน data URI (ไม่ต้องเก็บไฟล์) — เอาไปใส่ <img src> ได้ทันที"""

    @classmethod
    def qr_payload(cls, amount):
        """payload สตริง EMVCo สำหรับพร้อมเพย์ (ป้อนให้ lib qrcode / deep-link).

        Args:
            amount: จำนวนเงินบาท (float/str/Decimal)

        Returns:
            str payload EMVCo หรือ None ถ้า lib promptpay_qr ไม่ติดตั้ง/error
        """
        try:
            import promptpay_qr
            return promptpay_qr.generate_payload(settings.PROMPTPAY_ID, float(amount))
        except Exception:
            return None

    @classmethod
    def qr_data_uri(cls, amount):
        """data URI PNG ของ QR ที่นำไปใส่ <img src> ได้ทันที (ไม่เก็บไฟล์บนดิสก์).

        Args:
            amount: จำนวนเงินบาท

        Returns:
            str 'data:image/png;base64,...' หรือ None เมื่อ payload/lib ไม่พร้อม
        """
        try:
            import qrcode
            payload = cls.qr_payload(amount)
            if not payload:
                return None
            img = qrcode.make(payload)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception:
            return None


class QrCode:
    """QR จากข้อความทั่วไป → data URI (PNG) ด้วยไลบรารี qrcode ฝั่งเซิร์ฟเวอร์.

    ใช้แทนการโหลดไลบรารี QR จาก CDN ภายนอก — ทำงานได้แม้ออฟไลน์ และไม่พึ่ง third-party
    (dashboard ใช้สร้าง QR "เปิดระบบบนมือถือ" จาก URL จริงที่ build_absolute_uri).
    """

    @staticmethod
    def data_uri(text, box_size=4, border=2):
        """คืน 'data:image/png;base64,...' สำหรับ <img src> หรือ None ถ้าสร้างไม่ได้.

        Args:
            text: ข้อความ/URL ที่จะเข้ารหัสเป็น QR
            box_size: ขนาดโมดูล (พิกเซล) — 4 ให้ภาพ ~130px สำหรับ URL สั้น
            border: ขอบ Quiet zone (โมดูล)

        Returns:
            str | None
        """
        if not text:
            return None
        try:
            import qrcode
            qr = qrcode.QRCode(box_size=box_size, border=border)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception:
            return None


class SlipOK:
    """ตรวจสลิปโอนเงินด้วย SlipOK OCR API (https://slipok.com — มี free tier)
    SLIPOK_API_KEY ว่าง = ฟีเจอร์ถูกซ่อน (pattern เดียวกับ GeminiAI)"""

    API_URL = 'https://api.slipok.com/api/line-api/v3/uploadSlip'

    @classmethod
    def enabled(cls):
        """ฟีเจอร์ OCR พร้อมใช้หรือไม่ (ตั้ง SLIPOK_API_KEY ไว้หรือเปล่า).

        Returns:
            bool — False แปลว่า view จะซ่อนปุ่มอัปโหลดสลิป (degrade สวยงาม)
        """
        return bool(getattr(settings, 'SLIPOK_API_KEY', ''))

    @staticmethod
    def _multipart(fields, filename, content):
        """สร้าง multipart/form-data body ด้วย stdlib — ไม่เพิ่ม dependency.

        Args:
            fields: dict ฟิลด์ข้อความ (name → value)
            filename: ชื่อไฟล์ที่แนบ (SlipOK ดูจากชื่อเป็นหลัก)
            content: bytes เนื้อหาไฟล์สลิป

        Returns:
            tuple (body: bytes, boundary: str) สำหรับใส่ header Content-Type
        """
        import uuid
        boundary = '----thammathad' + uuid.uuid4().hex[:16]
        parts = []
        for k, v in fields.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8')
            )
        parts.append((
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n'
        ).encode('utf-8') + content + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
        return b''.join(parts), boundary

    @classmethod
    def verify(cls, image_content, filename='slip.jpg'):
        """ส่งรูปสลิปไป OCR ที่ SlipOK แล้วคืนข้อมูลการโอนที่อ่านได้.

        Args:
            image_content: bytes ของไฟล์ภาพสลิป
            filename: ชื่อไฟล์ที่แนบ (default 'slip.jpg')

        Returns:
            dict {amount: Decimal, transfer_date: str 'YYYY-MM-DD', note: str}
            note สร้างจากธนาคาร/ผู้โอน/ผู้รับ ให้โชว์บนหน้าสลิปได้เลย

        Raises:
            RuntimeError: เมื่อไม่มี API key ('no-api-key') หรือ SlipOK ตอบ
                          ไม่สำเร็จ — view ดักแล้วแปลงเป็นข้อความภาษาไทย
        """
        if not cls.enabled():
            raise RuntimeError('no-api-key')
        body, boundary = cls._multipart({'log': 'true'}, filename, image_content)
        req = urllib.request.Request(
            cls.API_URL, data=body,
            headers={
                'x-authorization': settings.SLIPOK_API_KEY,
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'User-Agent': 'thammathad-shop/1.0',
            },
        )
        import urllib.error
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = json.loads(e.read().decode()).get('message', '')
            except Exception:
                pass
            raise RuntimeError(f'http-{e.code}: {detail}')
        if not result.get('success'):
            raise RuntimeError(result.get('message') or 'verify-failed')

        d = result.get('data', {})
        amount = Decimal(str(d.get('amount', '0')))
        raw_date = str(d.get('date') or '')[:10]
        sender = ((d.get('sender') or {}).get('name')
                  or (d.get('sender') or {}).get('account') or '')
        receiver = ((d.get('receiver') or {}).get('name')
                    or (d.get('receiver') or {}).get('account') or '')
        bits = []
        if d.get('bank'):
            bits.append(str(d['bank']))
        if sender:
            bits.append(f'จาก {sender}')
        if receiver:
            bits.append(f'เข้า {receiver}')
        note = ('สลิป OCR: ' + ' · '.join(bits)) if bits else 'สลิป OCR'
        return {'amount': amount, 'transfer_date': raw_date, 'note': note}


class GeminiAI:
    """คำอธิบายสินค้าจาก Google Gemini REST API (urllib — ไม่เพิ่ม dependency)
    GEMINI_API_KEY ว่าง = ฟีเจอร์ถูกซ่อนและ endpoint ตอบ 503"""

    @classmethod
    def enabled(cls):
        """ฟีเจอร์ AI พร้อมใช้หรือไม่ (ตั้ง GEMINI_API_KEY ไว้หรือเปล่า).

        Returns:
            bool — False แปลว่า endpoint AI ตอบ 503 และซ่อนปุ่มใน UI
        """
        return bool(getattr(settings, 'GEMINI_API_KEY', ''))

    @classmethod
    def describe_product(cls, name, category=''):
        """Generate คำอธิบายสินค้าภาษาไทย 1 ประโยค (Gemini REST ผ่าน urllib).

        view เรียกแล้วเก็บคำตอบไปให้เจ้าหน้าที่กด "ใช้คำอธิบายนี้" — ไม่เขียนทับ
        ฟอร์มอัตโนมัติ (เจ้าหน้าที่เป็นคนอนุมัติ).

        Args:
            name: ชื่อสินค้า (ตัดเหลือ 100 ตัวก่อนส่ง)
            category: หมวดหมู่สินค้า — ช่วยให้ AI ตอบเฉพาะบริบทร้านไอที

        Returns:
            str ประโยคคำอธิบายภาษาไทย (ลบ whitespace หัวท้ายแล้ว)

        Raises:
            ValueError: เนื้อหาถูกบล็อก (PROHIBITED_CONTENT) หรือ AI ตอบว่างเปล่า
        """
        prompt = f"เขียนคำอธิบายสินค้าภาษาไทยประโยคเดียวไม่เกิน 25 คำ: '{name[:100]}'"
        if category:
            prompt += f" (หมวดหมู่: {category[:50]})"
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")}:generateContent'
        )
        # Gemini 3.x เป็น thinking model — กำหนด thinkingLevel='low' ให้เร็ว
        # และ maxOutputTokens ต้องเผื่อ thinking tokens (ถ้าน้อยไปจะได้ข้อความว่าง/ตัดคำ)
        body = json.dumps({
            'systemInstruction': {'parts': [{'text':
                'You write Thai product descriptions for an online IT shop. '
                'Reply with ONLY the description sentence. No preamble, no options, '
                'no markdown, no quotes.'}]},
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0.7,
                'maxOutputTokens': 1024,
                'thinkingConfig': {'thinkingLevel': 'low'},
            },
        }).encode('utf-8')
        req = urllib.request.Request(
            url, data=body,
            headers={'Content-Type': 'application/json',
                     'x-goog-api-key': settings.GEMINI_API_KEY,   # header ปลอดภัยกว่า ?key= ใน URL
                     'User-Agent': 'thammathad-shop/1.0'},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        candidate = (data.get('candidates') or [{}])[0]
        if candidate.get('finishReason') == 'PROHIBITED_CONTENT':
            raise ValueError('prohibited content')
        text = ''.join(
            p.get('text', '')
            for p in candidate.get('content', {}).get('parts', [])
        ).strip()
        if not text:
            raise ValueError(f'empty response (finishReason={candidate.get("finishReason")})')
        return text


class Validators:
    """ตรวจข้อมูลผู้ใช้ที่ใช้ร่วมกันหลาย view"""

    PHONE_RE = re.compile(r'^0\d{8,9}$')   # มือถือ 10 หลัก / บ้าน 9 หลัก (0 นำ)

    @classmethod
    def normalize_phone(cls, raw):
        """ตัดทุกอย่างที่ไม่ใช่ตัวเลขออก — รองรับเบอร์แบบ 08x-xxx-xxxx.

        Args:
            raw: สตริงที่ผู้ใช้กรอก (อาจปน -, ช่องว่าง, วงเล็บ)

        Returns:
            str เฉพาะตัวเลข เช่น '0812345678'
        """
        return re.sub(r'\D', '', raw or '')

    @classmethod
    def valid_phone(cls, raw):
        """ตรวจว่าเป็นเบอร์โทรศัพท์ไทยที่ยอมรับ (ขึ้นต้น 0 + ยาว 9-10 หลัก).

        Args:
            raw: เบอร์ตามที่กรอก (ปกติส่งผ่าน normalize_phone)

        Returns:
            bool — จริงถ้ามือถือ 10 หลัก / เบอร์บ้าน 9 หลัก
        """
        return bool(cls.PHONE_RE.match(cls.normalize_phone(raw)))


class OrderStatusService:
    """สถานะออเดอร์เป็นบันไดขั้นเดียว (ห้ามข้าม/ถอยหลัง):
    pending → paid → shipped → delivered

    - move()     : เจ้าหน้าที่เลื่อนขั้น — ได้เฉพาะ "ขั้นถัดไป" และไม่ใช่ขั้นอัตโนมัติ
    - auto_move(): ระบบสั่งเปลี่ยนเอง (เช่น จ่ายครบ → paid) — ใช้ขั้นบันไดเดิม
    - ขั้น 'paid' เป็นขั้นอัตโนมัติ — เจ้าหน้าที่ตั้งด้วยมือไม่ได้ (ต้องจ่ายเงินครบ)
    """

    FLOW = {'pending': 'paid', 'paid': 'shipped', 'shipped': 'delivered'}
    AUTOMATIC = {'paid'}

    @classmethod
    def next_status(cls, status):
        """สถานะถัดไปตามบันได (มองจาก FLOW — แผนที่เงื่อนเดียว).

        Args:
            status: สถานะปัจจุบัน (key ของ FLOW)

        Returns:
            str สถานะถัดไป หรือ None ถ้าไม่มี (เช่น delivered = จบเส้นทางแล้ว)
        """
        return cls.FLOW.get(status)

    @classmethod
    def staff_options(cls, order):
        """ขั้นที่เจ้าหน้าที่เลื่อนไปได้จากสถานะนี้ (ว่าง = เลื่อนด้วยมือไม่ได้).

        ใช้คุม UI: เจ้าหน้าที่เห็นปุ่มเลื่อนเฉพาะเมื่อมีตัวเลือก —
        ขั้น 'paid' ที่เป็นขั้นอัตโนมัติจะไม่ถูกเสนอเป็นเป้าหมายเลย.

        Args:
            order: instance Order

        Returns:
            list → [สถานะถัดไป] หรือ [] (ห้ามเลื่อนด้วยมือ)
        """
        nxt = cls.FLOW.get(order.status)
        if not nxt or nxt in cls.AUTOMATIC:
            return []
        return [nxt]

    @classmethod
    def move(cls, order, to, actor='staff'):
        """เลื่อนสถานะฝั่งเจ้าหน้าที่ 1 ขั้นตามบันได — คืนผลพร้อมข้อความภาษาไทย.

        กติกาใบงาน: ข้ามขั้น/ถอยหลัง = ปฏิเสธทันที ไม่มีผลกับ DB;
        ขั้น "ชำระเงินแล้ว" ตั้งด้วยมือไม่ได้ — ต้องผ่าน PaymentService
        ให้ระบบขึ้นอัตโนมัติเมื่อจ่ายครบยอด.

        Args:
            order: instance Order ที่จะเลื่อนสถานะ
            to: สถานะปลายทางที่เจ้าหน้าที่ส่งมา (ต้องตรงกับขั้นถัดไปพอดี)
            actor: ผู้สั่ง (default 'staff' — สงวนไว้สำหรับส่วนขยาย)

        Returns:
            tuple (ok: bool, message_thai: str) — ok=False = ปฏิเสธ ไม่แตะ DB
        """
        label = dict(order.STATUS_CHOICES)
        if order.status == to:
            return False, 'สถานะเป็นอย่างนี้อยู่แล้ว'
        nxt = cls.FLOW.get(order.status)
        if nxt != to:
            hint = label.get(nxt, '')
            return False, (f'เปลี่ยนจาก "{order.get_status_display()}" ได้แค่เป็น "{hint}" '
                           f'(ห้ามข้ามขั้น / ห้ามถอยหลัง)')
        if to in cls.AUTOMATIC:
            return False, 'ขั้น "ชำระแล้ว" เจ้าหน้าที่เปลี่ยนด้วยมือไม่ได้ — ต้องจ่ายเงินครบให้ระบบขึ้นให้อัตโนมัติ'
        order.status = to
        order.save(update_fields=['status'])
        return True, f'เปลี่ยนสถานะเป็น "{order.get_status_display()}" แล้ว'

    @classmethod
    def auto_move(cls, order, to, actor='system'):
        """ระบบสั่งเปลี่ยนสถานะเอง (เช่น ระบบเห็นยอดครบ → paid) — คืน True ถ้าเปลี่ยนใหม่.

        ต่างจาก move() ตรงที่ยอมตั้ง "ขั้นอัตโนมัติ" (paid) ได้ แต่ยังห้ามข้าม
        ขั้น/ถอยหลัง — ถ้าโงผิดทิศทางจะ raise ให้ caller จับ (ไม่เก็บเงียบ).

        Args:
            order: instance Order
            to: สถานะปลายทาง (ต้องเป็นขั้นถัดไปตาม FLOW พอดี)
            actor: default 'system' (ระบุผู้ trigger ได้ เช่น payment:slip-ocr)

        Returns:
            True = เพิ่งเปลี่ยนสถานะจริง, False = อยู่สถานะนั้นอยู่แล้ว

        Raises:
            ValueError: ถ้า to ไม่ใช่ขั้นถัดไปตามบันได (ข้ามขั้น/ถอยหลัง)
        """
        if order.status == to:
            return False
        if cls.FLOW.get(order.status) != to:
            raise ValueError(f'auto transition ไม่ถูกต้อง: {order.status} → {to}')
        order.status = to
        order.save(update_fields=['status'])
        return True


class PaymentService:
    """จุดรับเงินจุดเดียว — ทุกช่องทาง (สลิป / ปุ่มโอน 1 คลิก / เจ้าหน้าที่ยืนยัน)
    จะต้องเรียกที่นี้: บันทึกยอดเข้า → ดูว่า "รวมครบยอดหรือยัง"
    ถ้าครบ → เลื่อนสถานะเป็น paid อัตโนมัติ (ผ่าน OrderStatusService.auto_move)
    """

    @classmethod
    def record_payment(cls, order, name, phone, amount, transfer_date, note='', source=''):
        """จุดรับเงินจุดเดียวของทุกช่องทาง — สลิป OCR / ปุ่มโอน 1 คลิก / เจ้าหน้าที่ยืนยัน.

        กติกาเงินของใบงานรวมอยู่ที่จุดนี้:
        1) บันทึกยอดจ่าย (Payment) ลง DB
        2) รวม "ยอดที่แจ้งสะสม" เปรียบเทียบกับยอดรวมออเดอร์
        3) ถ้าสถานะยัง pending และยอดสะสมครบ → OrderStatusService.auto_move
           ยกไป 'paid' อัตโนมัติ (เจ้าหน้าที่ตั้งขั้น 'paid' ด้วยมือไม่ได้)

        ความถูกต้องของยอดเงิน (เพิ่ม 3 ชั้น — เคยพลาดทั้ง 3):
        - **refuse เมื่อไม่ pending**: ออเดอร์ที่จ่ายแล้ว/ส่งแล้ว/ถึงมือแล้ว
          จะไม่รับยอดเพิ่ม — เคยเป็นช่องโหว่เพราะ `SlipVerifyView` ไม่เช็คสถานะ
          (ต่างจาก QuickPayView ที่เช็ค) ทำให้อัปโหลดสลิปใส่ออเดอร์ที่จ่ายแล้วได้
          → Payment ยอดเกินยอดรวม → รายงานการเงินเพี้ยนทันที
          *กันไว้ 2 ชั้น*: ที่ service (จุดเดียวจริง) + ที่ view (ตอบข้อความที่เข้าใจได้)
        - **atomic**: read-modify-write ทั้งก้อนอยู่ใน transaction เดียว
        - **lock แถวออเดอร์**: `select_for_update()` กัน 2 request พร้อมกันอ่าน
          `reported` ได้ค่าเดิมทั้งคู่ แล้วทั้งคู่ผ่านเงื่อนไข "ครบยอด"
          (SQLite ไม่มี row lock จริง แต่ DATABASES OPTIONS ตั้ง
          `transaction_mode='IMMEDIATE'` ให้เขียนทีละ transaction)

        Args:
            order: instance Order เป้าหมาย
            name: ชื่อผู้ชำระ
            phone: เบอร์ผู้ชำระ
            amount: ยอดที่จ่ายรอบนี้ (Decimal) — บวกรวมกับยอดก่อนหน้า กลไก "จ่ายบางส่วน"
            transfer_date: วันที่โอน
            note: บันทึกเสริม (เช่น ผล OCR)
            source: ระบุช่องทาง ('slip-ocr', 'button', ...) — เอาไปบันทึกใน actor

        Returns:
            dict {ok, error, payment, reported, remaining, just_paid, paid}:
            - ok: False = ปฏิเสธ (ออเดอร์ไม่รอชำระ) → payment เป็น None, ไม่แตะ DB
            - error: ข้อความไทยสำหรับแสดงผลเมื่อ ok=False
            - payment: instance Payment ใหม่ที่เพิ่งสร้าง
            - reported: ยอดแจ้งสะสมทั้งหมด
            - remaining: ยอดที่ยังขาด จากยอดรวม (0 = จ่ายครบแล้ว)
            - just_paid: เพิ่งปิดสถานะเป็น paid ในรอบนี้หรือไม่
            - paid: สถานะปัจจุบันของออเดอร์ = paid หรือยัง
        """
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)

            if locked.status != 'pending':
                # ออเดอร์ที่จ่ายแล้ว/ส่งแล้ว/ถึงมือแล้ว จะไม่รับยอดเพิ่ม
                # ไม่บันทึกอะไรลง DB เลย — กันยอดเกินจริง (ดูคำอธิบายข้างบน)
                return {
                    'ok': False,
                    'error': f'ออเดอร์ #{locked.id} ไม่ได้อยู่ในสถานะรอชำระเงิน '
                              f'(ตอนนี้คือ "{locked.get_status_display()}") '
                              f'— ไม่สามารถบันทึกยอดเพิ่มได้',
                    'payment': None,
                    'reported': locked.reported_total(),
                    'remaining': Decimal('0'),
                    'just_paid': False,
                    'paid': locked.status != 'pending',
                }

            payment = Payment.objects.create(
                order=locked, name=name, phone=phone,
                amount=amount, transfer_date=transfer_date, note=note,
            )
            reported = locked.reported_total()
            just_paid = False
            if reported >= locked.total:
                just_paid = OrderStatusService.auto_move(
                    locked, 'paid', actor=f'payment:{source or "record"}')

        return {
            'ok': True,
            'error': '',
            'payment': payment,
            'reported': reported,
            'remaining': max(locked.total - reported, Decimal('0')),
            'just_paid': just_paid,
            'paid': locked.status == 'paid',
        }


class Cart:
    """ตะกร้าสินค้าเก็บใน session — Encapsulation: view ไม่แตะ dict ลึกๆ อีกต่อไป
    รูปแบบเก็บ: {'<product_id>': qty, ...}

    lines() คืนรายการเฉพาะสินค้าที่ยังแสดงอยู่ (is_active) — สินค้าที่ถูกลบ/ซ่อน
    จะหายจากตะกร้าอัตโนมัติเมื่อคำนวณ โดยไม่ล้างข้อมูลใน session (พฤติกรรมเดิม)
    """

    SESSION_KEY = 'cart'

    def __init__(self, session):
        self._session = session
        self._raw = session.get(self.SESSION_KEY, {})

    # ---------- อ่าน ----------
    def lines(self):
        """รายการสินค้าในตะกร้า: [{'product', 'quantity', 'line_total'}, ...].

        ใช้ in_bulk ดึงสินค้าทีเดียวจบ (แก้ปัญหา N+1 ของเวอร์ชันเดิม).
        สินค้าที่ถูกลบ/ซ่อนจะถูกข้ามโดยไม่เก็บในผลลัพธ์ แต่ไม่ล้าง session —
        พฤติกรรมตั้งใจ (แถวหลุดเองตามธรรมชาติ ลูกค้าสั่งใหม่ได้เอง).

        Returns:
            list ของ dict แถวตะกร้า (เรียงตามลำดับที่ใส่เข้าระบบ)
        """
        if not self._raw:
            return []
        products = Product.objects.in_bulk([int(pid) for pid in self._raw])
        items = []
        for pid, qty in self._raw.items():
            p = products.get(int(pid))
            if p is None or not p.is_active:
                continue   # ลบ/ซ่อนแล้ว — ข้ามโดยไม่ล้าง session (พฤติกรรมเดิม)
            line_total = p.price * qty
            items.append({'product': p, 'quantity': qty, 'line_total': line_total})
        return items

    @property
    def total(self):
        """ยอดรวมทั้งตะกร้า (Decimal) — คำนวณจาก lines() ที่กรองสินค้าดีแล้ว.

        Returns:
            Decimal รวม line_total ที่เหลือในตะกร้า
        """
        return sum((line['line_total'] for line in self.lines()), Decimal('0'))

    @property
    def count(self):
        """จำนวน "ชิ้น" รวมสำหรับป้าย navbar — นับ qty ทุกแถว (ไม่ใช่จำนวนแถว).

        เช่น 2 แถว × 3 ชิ้น = 6 → โชว์ "6".

        Returns:
            int จำนวนชิ้นทั้งหมด
        """
        return sum(line['quantity'] for line in self.lines())

    @property
    def is_empty(self):
        """session ยังว่างทุกแถวหรือไม่ (นับรวมสินค้าที่ถูกลบอยู่ด้วย).

        ใช้เช็คก่อนเปิดหน้า cart/checkout — ไม่อ้าง .lines() ที่กรองสินค้าไปแล้ว.

        Returns:
            bool
        """
        return not self._raw

    # ---------- เขียน ----------
    def _persist(self):
        """เขียน raw dict กลับลง session หลังแก้ทุกครั้ง (จุดบันทึกจุดเดียว)."""
        self._session[self.SESSION_KEY] = self._raw

    def add(self, product, quantity):
        """เพิ่มจำนวนสินค้าลงตะกร้า (รวมกับที่อยู่ในตะกร้าแล้ว).

        Args:
            product: instance Product
            quantity: จำนวนที่จะเพิ่ม (บังคับ int, ต่ำสุด 1 — กันข้อมูลมั่วจาก form)

        Returns:
            True = เพิ่มสำเร็จ / False = จำนวนรวมเกิน stock (ไม่เพิ่ม ให้ UI เตือน)
        """
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        if quantity < 1:
            quantity = 1
        key = str(product.id)
        new_total = self._raw.get(key, 0) + quantity
        if new_total > product.stock:
            return False
        self._raw[key] = new_total
        self._persist()
        return True

    def remove(self, product_id):
        """ลบสินค้าออกจากตะกร้า (เงียบเมื่อสินค้าไม่เคยมี — ไม่ raise)."""
        self._raw.pop(str(product_id), None)
        self._persist()

    def update(self, product_id, quantity):
        """แก้จำนวนสินค้าในตะกร้า (ลิมิตไม่เกิน stock, ต่ำสุด 1).

        Args:
            product_id: id ของสินค้า
            quantity: จำนวนใหม่ (ถ้าไม่ใช่ตัวเลขจะไม่ทำอะไรเลย)

        Returns:
            None — เงียบเมื่อสินค้าไม่อยู่ในตะกร้า หรือ quantity ใช้ไม่ได้
        """
        key = str(product_id)
        if key not in self._raw:
            return
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return
        if quantity < 1:
            quantity = 1
        product = Product.objects.filter(id=product_id).first()
        if product and quantity > product.stock:
            quantity = product.stock
        self._raw[key] = quantity
        self._persist()

    def clear(self):
        """ล้างตะกร้าทั้งหมด (ใช้หลังสั่งซื้อสำเร็จ หรือล้างเมื่อ logout)."""
        self._session[self.SESSION_KEY] = {}

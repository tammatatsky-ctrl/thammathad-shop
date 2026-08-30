"""Service layer — ตรรกะข้ามโมดูลที่ "ไม่ใช่หน้าที่ของ view ใด view เดียว"
view ทำหน้าที่เรียกใช้ service เท่านั้น ไม่ใส่ business logic ไว้ใน view เอง.

สถาปัตยกรรม (map ทั้ง module):
- Cart        : ตะกร้าสินค้าใน session (cart / checkout / ปุ่มใส่ตะกร้า ใช้ object เดียวกัน)
- ThaiCalendar: คำทักทาย + วันที่แบบพุทธศักราช สำหรับแดชบอร์ด
- ExchangeRate: อัตราแลกเปลี่ยน THB→USD จาก external API (โชว์การ "เรียกใช้" API)
- PromptPay   : QR พร้อมเพย์สำหรับหน้าสั่งซื้อสำเร็จ
- SlipOK      : OCR ตรวจสลิปโอนเงิน (API key ว่าง = ฟีเจอร์ถูกซ่อน + view ซ่อน UI)
- GeminiAI    : ข้อความช่วยเขียนคำอธิบายสินค้า (Google Gemini REST API)
- Validators  : ตรวจ/แปลงข้อมูลผู้ใช้ที่ใช้ร่วมกันหลายหน้า
- OrderStatusService: บันไดสถานะขั้นเดียว (pending → paid → shipped → delivered)
                      กติกาใบงาน: ห้ามข้ามขั้น/ห้ามถอยหลัง, paid เป็นขั้นอัตโนมัติ
- PaymentService: จุดรับเงินจุดเดียว — ทุกช่องทางจ่ายเงินต้องเรียกที่นี้ แล้ว
                  ระบบดูเองว่า "ครบยอดหรือยัง" → ขยับสถานะ paid อัตโนมัติ

ทุก service ใช้ staticmethod/classmethod (ไม่ต้องสร้าง instance) —
รวมโค้ดที่เกี่ยวข้องเข้าด้วยกันและ test ได้อิสระจาก view.
"""
import base64
import io
import json
import re
import time
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import Payment, Product


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

        Args:
            order: instance Order เป้าหมาย
            name: ชื่อผู้ชำระ
            phone: เบอร์ผู้ชำระ
            amount: ยอดที่จ่ายรอบนี้ (Decimal) — บวกรวมกับยอดก่อนหน้า กลไก "จ่ายบางส่วน"
            transfer_date: วันที่โอน
            note: บันทึกเสริม (เช่น ผล OCR)
            source: ระบุช่องทาง ('slip-ocr', 'button', ...) — เอาไปบันทึกใน actor

        Returns:
            dict {payment, reported, remaining, just_paid, paid}:
            - payment: instance Payment ใหม่ที่เพิ่งสร้าง
            - reported: ยอดแจ้งสะสมทั้งหมด
            - remaining: ยอดที่ยังขาด จากยอดรวม (0 = จ่ายครบแล้ว)
            - just_paid: เพิ่งปิดสถานะเป็น paid ในรอบนี้หรือไม่
            - paid: สถานะปัจจุบันของออเดอร์ = paid หรือยัง
        """
        payment = Payment.objects.create(
            order=order, name=name, phone=phone,
            amount=amount, transfer_date=transfer_date, note=note,
        )
        reported = order.reported_total()
        just_paid = False
        if order.status == 'pending' and reported >= order.total:
            just_paid = OrderStatusService.auto_move(order, 'paid', actor=f'payment:{source or "record"}')
        return {
            'payment': payment,
            'reported': reported,
            'remaining': max(order.total - reported, Decimal('0')),
            'just_paid': just_paid,
            'paid': order.status == 'paid',
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

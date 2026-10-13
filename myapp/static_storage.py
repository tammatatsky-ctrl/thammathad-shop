"""Static storage ที่ใส่ cache-busting query (`?v=...`) ให้ URL ของไฟล์ static

ทำไมต้องมี (บั๊กที่ทำให้ "แก้แล้วผู้ใช้ไม่เห็น"):
    โปรเจกต์เคยใช้ `?v=N` ใน `{% static %}` แล้ว **ถอดออก** (recipe #2 ของ AGENTS.md)
    ตอนนี้ `{% static 'css/theme.css' %}` ได้ `/static/css/theme.css` เปล่า ๆ
    เบราว์เซอร์จึง cache ไฟล์เดิมไว้ → หลัง deploy ใหม่ ผู้ใช้ (รวมถึงอาจารย์)
    ยังเห็น CSS/JS **เวอร์ชันเก่า** ทั้งที่เซิร์ฟเวอร์มีไฟล์ใหม่แล้ว
    = "แก้ไม่มีผล" แบบที่ไล่เวลาเสีย (และเสียคะแนนในการส่งงาน)

ทำไมไม่ใช้ `ManifestStaticFilesStorage` (วิธีมาตรฐานของ Django):
    มันเปลี่ยน **ชื่อไฟล์** เป็น `theme.<hash>.css` ซึ่งจะทำให้ระบบ
    deferred FX ของโปรเจกต์พังทันที เพราะ `fx-boot.js` / `fx-assets.js`
    สร้าง URL เองตอน runtime จาก **สตริงคงที่** เช่น `"css/effects/fx-glass.css"`
    (ไม่ได้ผ่าน `{% static %}`) → ชี้ไปไฟล์ที่ไม่มีอยู่จริง = 404 ทั้งระบบเอฟเฟกต์
    วิธีนี้จึงใช้ query string แทน: ชื่อไฟล์ไม่เปลี่ยน (URL ที่ runtime สร้างยังใช้ได้)
    แต่แต่ละเวอร์ชันได้ URL ต่างกัน → เบราว์เซอร์โหลดใหม่ให้อัตโนมัติ

ค่าเวอร์ชันมาจากไหน (ไม่ต้องแก้มือทุกครั้งที่แก้ CSS):
    `STATIC_VERSION` คำนวณจาก mtime ของไฟล์ core (theme.css + motion-core.js
    + fx-boot.js) → แก้ไฟล์เหล่านี้เมื่อไหร่ เวอร์ชันเปลี่ยนเองอัตโนมัติ
    ถ้าอยากบังคับให้เปลี่ยนทุก deploy ให้ตั้ง env `STATIC_VERSION` เอง
"""
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """StaticFilesStorage ที่เติม `?v=<STATIC_VERSION>` ท้าย URL

    ตั้งใช้แทน default เฉพาะตอน production (DEBUG=False) — ตอน dev ปล่อยให้
    staticfiles serve สด ๆ เพื่อไม่ให้ต้อง collectstatic ทุกครั้งที่แก้ไฟล์
    """

    def url(self, name):
        """คืน URL ของไฟล์ static พร้อมพารามิเตอร์กัน cache

        Args:
            name: พาธใน static (เช่น 'css/theme.css')

        Returns:
            str: URL พร้อม `?v=<STATIC_VERSION>` (เว้นกรณี URL ภายนอก/มี ? อยู่แล้ว)
        """
        url = super().url(name)

        # URL ภายนอก (cdn/absolute) ไม่ต้องแตะ และไม่ควรพ่วง query
        if url.startswith(('http://', 'https://', '//', 'data:')):
            return url

        from django.conf import settings
        version = getattr(settings, 'STATIC_VERSION', None)
        if not version:
            return url

        sep = '&' if '?' in url else '?'
        return f'{url}{sep}v={version}'

"""AppConfig ของ myapp — ตั้งค่า SQLite ให้รับ concurrent access ได้จริง

ทำไมต้องมี (ปัญหาจริงของ SQLite บนเว็บที่มี request พร้อมกัน):
    SQLite เป็น single-writer ตามธรรมชาติ โหมด journal แบบ `delete` (ค่าเริ่มต้น)
    จะบล็อก **ผู้อ่านทั้งหมด** ตอนมีการเขียน แม้แต่การเปิดหน้าแคตตาล็อก —
    ผลคือเว็บค้างเป็นจังหวะ ๆ (บั๊กที่เจอตอนร้านมีคนคลิกพร้อมกัน)

    `journal_mode=WAL` (Write-Ahead Logging) เปลี่ยนให้:
      - ผู้อ่านอ่านไปต่อได้ระหว่างที่มีคนเขียน (ไม่ถูกบล็อก)
      - ผู้เขียนยังเป็นคนเดียว แต่ถูก serialize ที่ transaction_mode='IMMEDIATE'

    หมายเหตุ: WAL เป็นค่าที่ผูกกับไฟล์ฐานข้อมูล (คงอยู่ถาวร ไม่ต้องตั้งทุกครั้ง)
    และใช้ได้เฉพาะดิสก์ในเครื่อง — ถ้าย้ายไปใช้ PostgreSQL/MySQL การตั้งค่านี้
    จะถูกข้ามเองอย่างปลอดภัย (เช็ค ENGINE ก่อน)

    ต้องตั้งผ่าน signal `connection_created` เพราะ PRAGMA ต้องรัน "ต่อ connection"
    ไม่ใช่ครั้งเดียวตอน import (Django เปิด/ปิด connection ได้หลายครั้ง)
"""
from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.dispatch import receiver


class MyappConfig(AppConfig):
    """AppConfig ของ myapp — default ทั้งหมด (ไม่ปรับ verbose_name/app_label) + ตั้ง SQLite WAL."""

    name = 'myapp'

    def ready(self):
        """เปิดโหมด WAL ทุกครั้งที่ Django เปิด connection ใหม่ (รวมตอนรันเทสต์)"""
        # import ภายใน ready() เพราะตอน import AppConfig ยังไม่พร้อมใช้ models
        from myapp.models import Product  # noqa: F401  (บังคับให้ app registry พร้อม)

        connection_created.connect(_enable_sqlite_wal, dispatch_uid='myapp.sqlite_wal')


@receiver(connection_created)
def _enable_sqlite_wal(sender, connection, **kwargs):
    """ตั้ง PRAGMA journal_mode=WAL เฉพาะเมื่อเป็น SQLite (ข้าม backend อื่นทิ้ง)

    Args:
        sender: AppConfig ที่เป็นเจ้าของ connection
        connection: connection ที่เพิ่งถูกสร้าง

    Note:
        ถ้าไฟล์อยู่บน filesystem ที่ไม่รองรับ WAL (เช่นบาง network share)
        SQLite จะคืนค่าโหมดเดิมมาแทน — จึงตรวจผลลัพธ์ก่อน ไม่ raise
    """
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        mode = cursor.execute('PRAGMA journal_mode=WAL').fetchone()[0]
    if mode.lower() == 'wal':
        return
    # in-memory DB (ตอนรันเทสต์) จะตอบว่า "memory" — ไม่ใช่ปัญหา จึงไม่ต้องเตือน
    db_name = connection.settings_dict.get('NAME') or ''
    if ':memory:' in db_name or 'mode=memory' in db_name:
        return
    import logging
    logging.getLogger(__name__).warning(
        'เปิด SQLite WAL ไม่ได้ (ได้โหมด %s) — ร้านจะช้าลงตอนมี request พร้อมกัน '
        '(มักเกิดเมื่อ db.sqlite3 อยู่บน filesystem ที่ไม่รองรับ WAL)', mode)
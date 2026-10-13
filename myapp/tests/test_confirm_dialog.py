"""เทสต์กล่องยืนยัน (islandConfirm) — หัวข้อ/ไอคอน/โทนต้องตรงกับสิ่งที่กำลังทำ

บั๊กที่เคยเกิดจริง
    `islandConfirm()` ถูกออกแบบมาเพื่อ "การลบ" ฝังหัวข้อ "ยืนยันการลบ"
    ไอคอนถังขยะ และปุ่ม "ยืนยันลบ" ไว้ตายตัว
    พอใช้กับ superuser override (บังคับสถานะ "ชำระแล้ว") ผู้ใช้จึงเห็น
    **หัวข้อว่า "ยืนยันการลบ" + ไอคอนถังขยะ** ขณะกำลังจะเปลี่ยนสถานะการเงิน
    → อันตรายกว่าไม่มีกล่องยืนยันเลย เพราะทำให้เข้าใจว่ากำลังลบอะไร

กติกาที่ต้องคงไว้
    ทุกจุดที่เดิมเป็นการลบ ต้องยังได้กล่องยืนยันการลบเป๊ะ ๆ
    (ค่าเริ่มต้นของ islandConfirm ห้ามเปลี่ยน)
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from django.contrib.auth.models import User

from myapp.models import Order, OrderItem, Product

MOTION_JS = Path(settings.BASE_DIR) / 'myapp' / 'static' / 'js' / 'motion-core.js'
THEME_CSS = Path(settings.BASE_DIR) / 'myapp' / 'static' / 'css' / 'theme.css'


class ConfirmDialogDefaultsTest(TestCase):
    """ค่าเริ่มต้นต้องยังเป็นการลบ — จุดเดิมทั้งหมดในระบบห้ามเปลี่ยน"""

    def test_island_confirm_defaults_are_delete(self):
        js = MOTION_JS.read_text(encoding='utf-8')
        self.assertIn('var title = opts.title || "ยืนยันการลบ";', js)
        self.assertIn('var icon = opts.icon || "bi-trash3-fill";', js)
        self.assertIn('var okText = opts.okText || "ยืนยันลบ";', js)
        self.assertIn('var tone = opts.tone || "danger";', js)

    def test_every_tone_has_button_and_icon_styles(self):
        css = THEME_CSS.read_text(encoding='utf-8')
        for cls in ('.gc-btn-danger', '.gc-btn-warning', '.gc-btn-primary',
                    '.gc-tone-warning .gc-icon', '.gc-tone-primary .gc-icon'):
            self.assertIn(cls, css, f'ขาดสไตล์ {cls} — ปุ่มจะกดไม่มีสี')

    def test_confirm_opts_from_reads_all_four_attributes(self):
        js = MOTION_JS.read_text(encoding='utf-8')
        for attr in ('data-confirm-title', 'data-confirm-icon',
                     'data-confirm-ok', 'data-confirm-tone'):
            self.assertIn(attr, js, f'auto-wire ยังไม่อ่าน {attr}')


class OverrideConfirmDialogTest(TestCase):
    """ฟอร์ม override ต้องประกาศหัวข้อ/โทนของตัวเอง ไม่ใช่ใช้ค่าเริ่มต้นของการลบ"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='root', password='pw', email='root@example.com')
        self.product = Product.objects.create(
            name='สินค้า', price=100, stock=5)
        self.order = Order.objects.create(
            customer_name='ลูกค้า', phone='0812345678', address='กทม',
            total=100, payment_method='bank')
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1, price=100)

    def test_override_form_declares_its_own_dialog_text(self):
        self.client.force_login(self.superuser)
        html = self.client.get(
            f"/orders/{self.order.id}/").content.decode('utf-8')
        form = re.search(r'<form[^>]*class="superuser-override".*?</form>',
                         html, re.S)
        self.assertIsNotNone(form, 'ไม่พบฟอร์ม override')
        block = form.group(0)
        # ต้องไม่ใช้ค่าเริ่มต้น (การลบ) และต้องระบุของตัวเองครบ
        self.assertNotIn('bi-trash3-fill', block)
        self.assertIn('data-confirm-title="ยืนยันการบังคับสถานะ"', block)
        self.assertIn('data-confirm-icon="bi-shield-lock-fill"', block)
        self.assertIn('data-confirm-ok="บังคับเป็นชำระแล้ว"', block)
        self.assertIn('data-confirm-tone="warning"', block)

    def test_delete_buttons_do_not_override_the_defaults(self):
        """จุดอื่นที่เป็นการลบ ต้องไม่เพิ่ม attribute ใหม่ (กล่องยืนยันการลบ)"""
        html = (Path(settings.BASE_DIR) / 'myapp' / 'templates'
                / 'employee_list.html').read_text(encoding='utf-8')
        if 'data-confirm' in html:
            for m in re.finditer(r'<form[^>]*data-confirm[^>]*>', html):
                tag = m.group(0)
                self.assertNotIn('data-confirm-tone', tag,
                                 'จุดที่เป็นการลบไม่ควรเปลี่ยนโทน')
"""วาดไดอะแกรมทางวิศวกรรมซอฟต์แวร์เป็น `reportlab.graphics.shapes.Drawing`

มาตรฐานทางวิชาการ:
    - ใช้สีดำ ขาว และเฉดสีเทากลางเท่านั้น (Monochrome / Pure Black & White)
    - ไดอะแกรมทุกรูปวาดด้วยเวกเตอร์มาตรฐานสากล (UML Use Case, Layered Architecture, ERD, State Machine)
    - สามารถส่งออกได้ทั้งเวกเตอร์ PDF และภาพบิตแมป PNG สำหรับ Word
"""

from __future__ import annotations

import os
from typing import Iterable

from reportlab.graphics.shapes import (Circle, Drawing, Line, Polygon, Rect,
                                       String)
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------------------------------------------------------------------------
# ฟอนต์ไทย
# ---------------------------------------------------------------------------
THAI_FONT_CANDIDATES = [
    ('TH Sarabun New', 'C:/Windows/Fonts/THSARAB.TTF', 'C:/Windows/Fonts/THSARAB.TTF'),
    ('Sarabun', 'C:/Windows/Fonts/Sarabun-Regular.ttf', None),
    ('Leelawadee UI', 'C:/Windows/Fonts/LeelawUI.ttf', None),
    ('Leelawadee', 'C:/Windows/Fonts/leelawad.ttf', 'C:/Windows/Fonts/leelawdb.ttf'),
    ('Tahoma', 'C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/tahomabd.ttf'),
]

FONT_REGULAR = 'THAI'
FONT_BOLD = 'THAI-BOLD'
_font_ready = False


def register_thai_fonts() -> tuple[str, str]:
    """ลงทะเบียนฟอนต์ไทยกับ reportlab — เรียกซ้ำได้ ไม่มีผลซ้ำ"""
    global _font_ready
    if _font_ready:
        return FONT_REGULAR, FONT_BOLD

    errors = []
    for name, regular, bold in THAI_FONT_CANDIDATES:
        if not (regular and os.path.exists(regular)):
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular))
            pdfmetrics.registerFont(
                TTFont(FONT_BOLD, bold if bold and os.path.exists(bold) else regular))
            _font_ready = True
            return FONT_REGULAR, FONT_BOLD
        except Exception as exc:
            errors.append(f'{name}: {exc}')

    raise RuntimeError(
        'ไม่พบฟอนต์ที่รองรับภาษาไทยในเครื่องนี้\n'
        '  ต้องมีอย่างใดอย่างหนึ่ง: '
        + ', '.join(c[0] for c in THAI_FONT_CANDIDATES)
        + ('\n  ข้อผิดพลาด: ' + '; '.join(errors) if errors else '')
    )


def text_width(text: str, size: float, bold: bool = False) -> float:
    """คำนวณความกว้างของข้อความ"""
    try:
        font = FONT_BOLD if bold else FONT_REGULAR
        return pdfmetrics.stringWidth(text, font, size)
    except Exception:
        return len(text) * size * 0.55


def wrap(text: str, size: float, max_width: float, bold: bool = False,
         max_lines: int = 99) -> list[str]:
    """ตัดบรรทัดตามความกว้างที่กำหนดสำหรับภาษาไทย"""
    if not text:
        return ['']
    lines: list[str] = []
    current = ''
    for ch in text:
        if ch == '\n':
            lines.append(current)
            current = ''
            continue
        if text_width(current + ch, size, bold) <= max_width or not current:
            current += ch
        else:
            lines.append(current)
            current = ch
    lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, int(max_width / (size * 0.55)) - 1)] + '…'
    return lines


# ---------------------------------------------------------------------------
# จานสีทางวิชาการ (Monochrome / Grayscale — ใช้สีดำเป็นหลักตามข้อกำหนด)
# ---------------------------------------------------------------------------
INK = HexColor('#000000')          # สีดำมาตรฐานสำหรับเส้นและข้อความหลัก
INK_SOFT = HexColor('#000000')     # สีดำ
MUTED = HexColor('#000000')        # สีดำ
LINE = HexColor('#000000')         # สีดำสำหรับเส้นขอบ
PAPER = HexColor('#ffffff')        # สีขาวสำหรับพื้นหลัง
BLUE = HexColor('#000000')         # ดำ
BLUE_SOFT = HexColor('#f2f2f2')    # เทาอ่อนสำหรับพื้นหลังส่วนหัว
GREEN = HexColor('#000000')        # ดำ
GREEN_SOFT = HexColor('#f2f2f2')   # เทาอ่อน
AMBER = HexColor('#000000')        # ดำ
AMBER_SOFT = HexColor('#f2f2f2')   # เทาอ่อน
RED = HexColor('#000000')          # ดำ
RED_SOFT = HexColor('#f2f2f2')     # เทาอ่อน
GREY_SOFT = HexColor('#f5f5f5')    # เทาอ่อน
PURPLE = HexColor('#000000')       # ดำ
PURPLE_SOFT = HexColor('#f2f2f2')  # เทาอ่อน


def text(draw: Drawing, x: float, y: float, value: str, size: float = 9,
         color: Color = INK, bold: bool = False, align: str = 'left',
         width: float = 0) -> None:
    """วางข้อความ 1 บรรทัด (รองรับจัดกึ่งกลาง/ขวา)"""
    if align == 'center':
        x = x + width / 2 - text_width(value, size, bold) / 2
    elif align == 'right':
        x = x + width - text_width(value, size, bold)
    draw.add(String(x, y, value,
                    fontName=FONT_BOLD if bold else FONT_REGULAR,
                    fontSize=size, fillColor=color))


def arrow(draw: Drawing, x1: float, y1: float, x2: float, y2: float,
          color: Color = INK, width: float = 1.0,
          head: float = 5.0, dashed: bool = False) -> None:
    """วาดเส้นเชื่อมโยงพร้อมหัวลูกศรทึบ"""
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    bx, by = x2 - ux * head * 0.9, y2 - uy * head * 0.9
    line = Line(x1, y1, bx, by, strokeColor=color, strokeWidth=width)
    if dashed:
        line.strokeDashArray = [3, 2]
    draw.add(line)
    px, py = -uy, ux
    draw.add(Polygon([x2, y2,
                      bx + px * head * 0.42, by + py * head * 0.42,
                      bx - px * head * 0.42, by - py * head * 0.42],
                     fillColor=color, strokeColor=None))


def box(draw: Drawing, x: float, y: float, w: float, h: float,
        title: str, subtitle: str = '', fill: Color = PAPER,
        stroke: Color = LINE, accent: Color | None = None,
        title_size: float = 9.5) -> float:
    """กล่องหัวข้อมาตรฐาน"""
    sub_lines = wrap(subtitle, 7.2, w - 14) if subtitle else []
    h = max(h, 20 + len(sub_lines) * 9)
    draw.add(Rect(x, y, w, h, rx=3, ry=3,
                  fillColor=fill, strokeColor=stroke, strokeWidth=1.0))
    if accent:
        draw.add(Rect(x, y + 2, 3, h - 4, rx=1, ry=1,
                      fillColor=accent, strokeColor=None))
    text(draw, x + 8, y + h - 12, title, title_size, INK, bold=True)
    for i, line in enumerate(sub_lines):
        text(draw, x + 8, y + h - 22 - i * 9, line, 7.2, INK)
    return h


def note(draw: Drawing, x: float, y: float, w: float, msg: str,
         fill: Color = PAPER, stroke: Color = LINE,
         color: Color = INK, size: float = 7.4) -> float:
    """กล่องหมายเหตุหรือคำอธิบายประกอบภาพ"""
    lines = wrap(msg, size, w - 16)
    h = 8 + len(lines) * 9.2
    draw.add(Rect(x, y, w, h, rx=2, ry=2,
                  fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
    for i, line in enumerate(lines):
        text(draw, x + 8, y + h - 10 - i * 9.2, line, size, color)
    return h


def actor_figure(draw: Drawing, x: float, y: float, label: str, sublabel: str = '') -> None:
    """วาดสัญลักษณ์ Actor ตามมาตรฐาน UML (Stick Figure)"""
    # หัว (วงกลม)
    draw.add(Circle(x, y + 24, 8, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.2))
    # ลำตัว
    draw.add(Line(x, y + 16, x, y - 6, strokeColor=LINE, strokeWidth=1.2))
    # แขน
    draw.add(Line(x - 14, y + 6, x + 14, y + 6, strokeColor=LINE, strokeWidth=1.2))
    # ขาซ้ายและขาขวา
    draw.add(Line(x, y - 6, x - 10, y - 22, strokeColor=LINE, strokeWidth=1.2))
    draw.add(Line(x, y - 6, x + 10, y - 22, strokeColor=LINE, strokeWidth=1.2))
    # ป้ายกำกับ
    text(draw, x, y - 33, label, 8.5, INK, bold=True, align='center')
    if sublabel:
        text(draw, x, y - 43, sublabel, 7.2, INK, align='center')


def usecase_oval(draw: Drawing, cx: float, cy: float, w: float, h: float,
                 label: str, code: str = '') -> None:
    """วาด Use Case รูปวงรี/ขอบมนตามมาตรฐาน UML"""
    draw.add(Rect(cx - w / 2, cy - h / 2, w, h, rx=h / 2, ry=h / 2,
                  fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    if code:
        text(draw, cx, cy + 3, code, 6.8, INK, bold=True, align='center')
        text(draw, cx, cy - 7, label, 7.4, INK, bold=False, align='center')
    else:
        text(draw, cx, cy - 2.5, label, 7.6, INK, bold=False, align='center')


# ---------------------------------------------------------------------------
# ไดอะแกรม 1: Use Case Diagram (มาตรฐาน UML)
# ---------------------------------------------------------------------------
def use_case_diagram(cases: dict[str, list[tuple[str, str]]],
                     title: str = 'Use Case Diagram') -> Drawing:
    """แผนภาพกรณีการใช้งานตามมาตรฐาน UML (Use Case Diagram)"""
    width = 520
    height = 360
    d = Drawing(width, height)

    # 1. ขอบเขตระบบ (System Boundary)
    sys_x, sys_y, sys_w, sys_h = 105, 20, 310, 315
    d.add(Rect(sys_x, sys_y, sys_w, sys_h, rx=4, ry=4,
               fillColor=PAPER, strokeColor=LINE, strokeWidth=1.2))
    text(d, sys_x + 12, sys_y + sys_h - 16,
         'ระบบร้านค้าออนไลน์ THAMMATHAD SHOP (System Boundary)', 9, INK, bold=True)

    # 2. ผู้กระทำ (Actors)
    cust_x, cust_y = 52, 185
    actor_figure(d, cust_x, cust_y, 'ลูกค้า', '(Customer)')

    staff_x, staff_y = 468, 185
    actor_figure(d, staff_x, staff_y, 'เจ้าหน้าที่ / ผู้ดูแล', '(Staff / Admin)')

    # 3. Use Cases
    # กลุ่มฝั่งลูกค้า (ซ้าย)
    customer_cases = [
        ('UC-01', 'สืบค้นและดูแคตตาล็อกสินค้า', 265),
        ('UC-02', 'จัดการตะกร้าและสั่งซื้อสินค้า', 215),
        ('UC-03', 'ชำระเงินและแจ้งโอน (QR / สลิป)', 165),
        ('UC-04', 'ติดตามและยืนยันการรับพัสดุ', 115),
        ('UC-05', 'จัดการข้อมูลส่วนตัวและที่อยู่', 65),
    ]

    # กลุ่มฝั่งเจ้าหน้าที่ (ขวา)
    staff_cases = [
        ('UC-06', 'จัดการข้อมูลสินค้าและสต็อกคงคลัง', 265),
        ('UC-07', 'ตรวจสอบยอดชำระเงินและบัญชี', 215),
        ('UC-08', 'ปรับปรุงสถานะจัดส่งพัสดุสินค้า', 165),
        ('UC-09', 'ตรวจสอบบันทึกการทำงาน (Audit Trail)', 115),
        ('UC-10', 'จัดการบัญชีพนักงานและสิทธิ์เข้าใช้', 65),
    ]

    col1_cx = sys_x + 78
    col2_cx = sys_x + sys_w - 78
    oval_w, oval_h = 138, 36

    # วาด Use Cases ลูกค้า และเส้นเชื่อมโยง
    for code, label, cy in customer_cases:
        usecase_oval(d, col1_cx, cy, oval_w, oval_h, label, code)
        # เส้นความสัมพันธ์ (Association) จาก Customer ไป Use Case
        d.add(Line(cust_x + 15, cust_y, col1_cx - oval_w / 2, cy,
                   strokeColor=LINE, strokeWidth=0.8))

    # วาด Use Cases เจ้าหน้าที่ และเส้นเชื่อมโยง
    for code, label, cy in staff_cases:
        usecase_oval(d, col2_cx, cy, oval_w, oval_h, label, code)
        # เส้นความสัมพันธ์ (Association) จาก Staff ไป Use Case
        d.add(Line(staff_x - 15, staff_y, col2_cx + oval_w / 2, cy,
                   strokeColor=LINE, strokeWidth=0.8))

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 2: สถาปัตยกรรมแบบ 4 ชั้น (4-Layer System Architecture)
# ---------------------------------------------------------------------------
def layered_architecture() -> Drawing:
    """แผนภาพสถาปัตยกรรมระบบแบบ 4 ชั้น (Layered Architecture) เชิงวิชาการ"""
    w = 520
    h = 330
    d = Drawing(w, h)

    layers = [
        ('1. ชั้นนำเสนอ (Presentation Layer)',
         'ส่วนต่อประสานเว็บ (HTML5, Liquid Glass CSS, Motion Core JS) · ส่วนบริการ REST API (Django REST Framework)'),
        ('2. ชั้นควบคุมและตรรกะมุมมอง (View & Logic Layer)',
         'Django Class-Based Views (CBVs) · การควบคุมสิทธิ์ (StaffRequiredMixin, RBAC) · API ViewSets · Token Throttling'),
        ('3. ชั้นบริการทางธุรกิจ (Business Service Layer)',
         'PaymentService (จุดรับเงินจุดเดียว) · OrderStatusService (เครื่องจักรสถานะคำสั่งซื้อ) · Audit · RateLimit · SlipOK · PromptPay'),
        ('4. ชั้นการเข้าถึงและจัดเก็บข้อมูล (Data Access & Persistence Layer)',
         'Django Object-Relational Mapping (ORM) · Custom QuerySets & Managers · ฐานข้อมูลเชิงสัมพันธ์ SQLite'),
    ]

    box_w, box_h = 420, 52
    box_x = 20
    gap = 14
    y = h - 25

    for i, (title_text, desc_text) in enumerate(layers):
        cur_y = y - box_h
        # กล่องหลัก
        d.add(Rect(box_x, cur_y, box_w, box_h, rx=2, ry=2,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
        # แถบหัวข้อชั้น
        d.add(Rect(box_x, cur_y + box_h - 18, box_w, 18, rx=2, ry=2,
                   fillColor=HexColor('#eeeeee'), strokeColor=LINE, strokeWidth=0.8))
        text(d, box_x + 10, cur_y + box_h - 13, title_text, 8.8, INK, bold=True)

        # รายละเอียดภายในชั้น
        desc_lines = wrap(desc_text, 7.3, box_w - 20)
        for li, line in enumerate(desc_lines):
            text(d, box_x + 10, cur_y + box_h - 29 - li * 9.5, line, 7.3, INK)

        # ลูกศรชี้ลงระหว่างชั้น
        if i < len(layers) - 1:
            arrow(d, box_x + box_w / 2, cur_y - 1, box_x + box_w / 2, cur_y - gap + 3,
                  color=INK, width=1.0)

        y -= box_h + gap

    # เส้นแสดงทิศทางการเรียกและการพึ่งพา (Dependency Flow)
    flow_x = 465
    arrow(d, flow_x, h - 35, flow_x, 60, color=INK, width=1.2, head=6.0)
    text(d, flow_x + 6, h / 2 + 15, 'ทิศทางการเรียกใช้งาน', 7.5, INK, bold=True)
    text(d, flow_x + 6, h / 2 + 3, '(Top-Down Invocation)', 6.8, INK)
    text(d, flow_x + 6, h / 2 - 12, 'ห้ามขึ้นต่อกันแบบย้อนกลับ', 6.8, INK)

    # หมายเหตุเชิงวิชาการ
    note(d, box_x, 8, box_w,
         'หลักการออกแบบ: รวมศูนย์ตรรกะทางธุรกิจไว้ที่ชั้น Service เท่านั้น (Single Source of Truth) '
         'โดย View ทำหน้าที่เป็นเพียงตัวรับส่งคำขอและผลลัพธ์',
         fill=PAPER, stroke=LINE, color=INK, size=7.2)

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 3: แผนภาพการเปลี่ยนสถานะของคำสั่งซื้อ (Order State Machine)
# ---------------------------------------------------------------------------
def order_lifecycle_diagram(statuses: list[tuple[str, str]],
                            actors: list[str]) -> Drawing:
    """แผนภาพการเปลี่ยนสถานะคำสั่งซื้อตามมาตรฐาน UML State Transition"""
    width = 520
    height = 250
    d = Drawing(width, height)

    main_y = 160
    state_w, state_h = 82, 38

    # 1. Initial State (วงกลมทึบ)
    d.add(Circle(30, main_y, 6, fillColor=INK, strokeColor=None))
    arrow(d, 36, main_y, 65, main_y, color=INK, width=1.0)
    text(d, 50, main_y + 8, 'สั่งซื้อ', 6.8, INK, bold=True, align='center')

    # ลำดับสถานะหลักในบันไดทางเดียว
    steps = [
        ('รอชำระเงิน', '[PENDING]', 65),
        ('ชำระเงินแล้ว', '[PAID]', 175),
        ('จัดส่งแล้ว', '[SHIPPED]', 285),
        ('ถึงมือแล้ว', '[DELIVERED]', 395),
    ]

    # วาดสถานะหลัก
    for label, code, sx in steps:
        d.add(Rect(sx, main_y - state_h / 2, state_w, state_h, rx=4, ry=4,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
        text(d, sx + state_w / 2, main_y + 3, label, 7.8, INK, bold=True, align='center')
        text(d, sx + state_w / 2, main_y - 9, code, 6.8, INK, align='center')

    # เส้นเปลี่ยนสถานะระหว่างขั้นตอนหลัก
    transitions = [
        (65 + state_w, 175, 'ชำระเงินครบถ้วน (ระบบ)', '(PaymentService)'),
        (175 + state_w, 285, 'จัดส่งพัสดุ', '(เจ้าหน้าที่บันทึก)'),
        (285 + state_w, 395, 'ได้รับของเรียบร้อย', '(ลูกค้ายืนยันรับ)'),
    ]
    for x1, x2, tlabel, tsub in transitions:
        arrow(d, x1, main_y, x2, main_y, color=INK, width=1.0)
        text(d, (x1 + x2) / 2, main_y + 11, tlabel, 6.6, INK, bold=True, align='center')
        text(d, (x1 + x2) / 2, main_y + 2, tsub, 6.0, INK, align='center')

    # ชี้ไปยัง Final State สำหรับออเดอร์ที่สำเร็จ
    fin_x = 495
    arrow(d, 395 + state_w, main_y, fin_x - 10, main_y, color=INK, width=1.0)
    # Final State 1 (Bullseye: วงกลมซ้อน)
    d.add(Circle(fin_x, main_y, 7, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    d.add(Circle(fin_x, main_y, 4, fillColor=INK, strokeColor=None))
    text(d, fin_x, main_y - 18, 'เสร็จสมบูรณ์', 6.5, INK, align='center')

    # กิ่งสถานะยกเลิก (Branch: CANCELLED)
    canc_x, canc_y = 65, 60
    # ลูกศรชี้ลงจาก รอชำระเงิน มายัง ยกเลิก
    arrow(d, 65 + state_w / 2, main_y - state_h / 2, 65 + state_w / 2, canc_y + state_h / 2,
          color=INK, width=1.0)
    text(d, 65 + state_w / 2 + 4, (main_y + canc_y) / 2 - 2, 'ลูกค้ายกเลิก', 6.5, INK)

    # กล่องสถานะยกเลิก
    d.add(Rect(canc_x, canc_y - state_h / 2, state_w, state_h, rx=4, ry=4,
               fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    text(d, canc_x + state_w / 2, canc_y + 3, 'ยกเลิกคำสั่งซื้อ', 7.8, INK, bold=True, align='center')
    text(d, canc_x + state_w / 2, canc_y - 9, '[CANCELLED]', 6.8, INK, align='center')

    # ชี้จากยกเลิกไปยัง Final State 2
    arrow(d, canc_x + state_w, canc_y, 220, canc_y, color=INK, width=1.0)
    d.add(Circle(228, canc_y, 7, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    d.add(Circle(228, canc_y, 4, fillColor=INK, strokeColor=None))
    text(d, 228, canc_y - 17, 'ยุติคำสั่งซื้อ', 6.5, INK, align='center')

    # หมายเหตุกฎเกณฑ์ทางธุรกิจ
    note(d, 20, 8, width - 40,
         'กฎเกณฑ์ความถูกต้อง (Invariants): การเปลี่ยนสถานะเป็นไปตามบันไดทิศทางเดียว (Monotonic Transition) '
         'ห้ามข้ามขั้นตอนและห้ามย้อนกลับ สถานะ PAID เกิดขึ้นอัตโนมัติเมื่อยอดชำระครบถ้วนผ่าน PaymentService เท่านั้น',
         fill=PAPER, stroke=LINE, color=INK, size=7.2)

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 4: แผนภาพแบบจำลองข้อมูลเชิงสัมพันธ์ (Relational Schema / ERD)
# ---------------------------------------------------------------------------
def er_diagram(models: Iterable, title: str = 'ER Diagram') -> Drawing:
    """แผนภาพแบบจำลองข้อมูลเชิงสัมพันธ์ (Relational Schema Diagram / ERD)"""
    models = list(models)
    cols = 3
    gap_x, gap_v = 24, 22
    box_w = 152
    rows = (len(models) + cols - 1) // cols

    def _visible(m) -> list:
        return [f for f in m.fields
                if f.primary_key or f.is_fk
                or f.name in ('status', 'total', 'amount', 'kind',
                              'emp_code', 'name', 'price')][:4]

    heights = []
    for m in models:
        n = len(_visible(m))
        heights.append(28 + max(n, 1) * 11 + 6)

    row_h = [max(heights[r * cols:(r + 1) * cols] or [40]) for r in range(rows)]
    width = cols * box_w + (cols - 1) * gap_x + 36
    legend_h = 20
    top_pad = 28
    height = sum(row_h) + (rows - 1) * gap_v + top_pad + legend_h + 16

    d = Drawing(width, height)

    positions: dict[str, tuple[float, float, float]] = {}
    row_top: list[float] = []
    cursor = height - top_pad
    for h_val in row_h:
        cursor -= h_val
        row_top.append(cursor)
        cursor -= gap_v

    for i, m in enumerate(models):
        col, row = i % cols, i // cols
        x = 18 + col * (box_w + gap_x)
        y = row_top[row]
        bh = row_h[row]
        positions[m.name] = (x, y, bh)

        # กรอบตารางหลัก
        d.add(Rect(x, y, box_w, bh, rx=2, ry=2,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
        # ส่วนหัวตาราง (เทาอ่อน)
        d.add(Rect(x, y + bh - 16, box_w, 16, rx=2, ry=2,
                   fillColor=HexColor('#eeeeee'), strokeColor=LINE, strokeWidth=0.8))
        text(d, x + 8, y + bh - 12, m.name, 8.5, INK, bold=True)

        shown = _visible(m)
        for j, f in enumerate(shown):
            ty = y + bh - 28 - j * 11
            prefix = '[PK] ' if f.primary_key else ('[FK] ' if f.is_fk else '     ')
            field_str = f'{prefix}{f.name} : {f.short_type}'
            text(d, x + 6, ty, field_str, 6.6, INK, bold=f.primary_key)

    # วาดเส้นเชื่อมโยงความสัมพันธ์ (Foreign Key Lines)
    drawn: set[tuple[str, str]] = set()
    for m in models:
        for f in m.fk_fields:
            target = next((o for o in models if o.name in (f.fk_target or '')), None)
            if target is None or (target.name, m.name) in drawn:
                continue
            drawn.add((target.name, m.name))
            ax, ay = _edge_point(positions[target.name], positions[m.name],
                                 box_w, positions[target.name][2])
            bx, by = _edge_point(positions[m.name], positions[target.name],
                                 box_w, positions[m.name][2])
            arrow(d, ax, ay, bx, by, color=INK, width=0.8, dashed=True)

    # คำอธิบายสัญลักษณ์ทางวิชาการ
    ly = 10
    text(d, 20, ly, '[PK] = คีย์หลัก (Primary Key)      [FK] = คีย์นอก (Foreign Key)', 7.0, INK, bold=True)
    arrow(d, 230, ly + 3, 260, ly + 3, color=INK, width=0.8, dashed=True)
    text(d, 265, ly, 'เส้นประแสดงความสัมพันธ์การอ้างอิงระหว่างตาราง (FK Dependency: N -> 1)', 7.0, INK)

    return d


def _edge_point(frm: tuple[float, float], to: tuple[float, float],
                box_w: float, box_h: float) -> tuple[float, float]:
    """คำนวณจุดตัดบนขอบกล่องระหว่าง 2 จุด"""
    x0, y0 = frm[0] + box_w / 2, frm[1] + box_h / 2
    x1, y1 = to[0] + box_w / 2, to[1] + box_h / 2
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return x0, y0
    tx = (box_w / 2) / abs(dx) if dx else float('inf')
    ty = (box_h / 2) / abs(dy) if dy else float('inf')
    t = min(tx, ty)
    return x0 + dx * t, y0 + dy * t
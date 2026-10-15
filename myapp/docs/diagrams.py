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
_local_appdata = os.environ.get('LOCALAPPDATA', '')
_user_fonts = os.path.join(_local_appdata, 'Microsoft', 'Windows', 'Fonts') if _local_appdata else ''

THAI_FONT_CANDIDATES = [
    ('TH Sarabun New (User)',
     os.path.join(_user_fonts, 'THSarabunNew.ttf') if _user_fonts else '',
     os.path.join(_user_fonts, 'THSarabunNew Bold.ttf') if _user_fonts else ''),
    ('TH Sarabun New (Windows)', 'C:/Windows/Fonts/THSarabunNew.ttf', 'C:/Windows/Fonts/THSarabunNew Bold.ttf'),
    ('TH Sarabun (Windows)', 'C:/Windows/Fonts/THSarabun.ttf', 'C:/Windows/Fonts/THSarabun Bold.ttf'),
    ('TH Sarabun PSK', 'C:/Windows/Fonts/THSARAB.TTF', 'C:/Windows/Fonts/THSARAB.TTF'),
    ('Sarabun', 'C:/Windows/Fonts/Sarabun-Regular.ttf', None),
    ('Leelawadee UI', 'C:/Windows/Fonts/LeelawUI.ttf', None),
    ('Leelawadee', 'C:/Windows/Fonts/leelawad.ttf', 'C:/Windows/Fonts/leelawdb.ttf'),
    ('Tahoma', 'C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/tahomabd.ttf'),
]

FONT_REGULAR = 'THAI'
FONT_BOLD = 'THAI-BOLD'
_font_ready = False


# ---------------------------------------------------------------------------
# กลไกจัดตำแหน่งสระและวรรณยุกต์ไทย (Thai PUA Glyph Shaping)
# ป้องกันปัญหาสระและวรรณยุกต์ซ้อนกันหรือชนหางพยัญชนะ (ตัวสระซ้อนกัน)
# ---------------------------------------------------------------------------
_ASCENDER = set('\u0e1b\u0e1d\u0e1f\u0e2c')  # ป ฝ ฟ ฬ
_DESCENDER = set('\u0e0e\u0e0f')              # ฎ ฏ
_PEDESTAL = {'\u0e0d': '\uf70f', '\u0e10': '\uf700'}  # ญ ฐ

_UPPER_VOWEL = set('\u0e31\u0e34\u0e35\u0e36\u0e37\u0e47\u0e4d')
_UPPER_VOWEL_LEFT = {
    '\u0e34': '\uf701', '\u0e35': '\uf702', '\u0e36': '\uf703', '\u0e37': '\uf704',
    '\u0e31': '\uf710', '\u0e4d': '\uf711', '\u0e47': '\uf712'
}

_TONE = set('\u0e48\u0e49\u0e4a\u0e4b\u0e4c')
_TONE_LEFT = {
    '\u0e48': '\uf705', '\u0e49': '\uf706', '\u0e4a': '\uf707', '\u0e4b': '\uf708', '\u0e4c': '\uf709'
}
_TONE_UP = {
    '\u0e48': '\uf713', '\u0e49': '\uf714', '\u0e4a': '\uf715', '\u0e4b': '\uf716', '\u0e4c': '\uf717'
}
_TONE_UP_LEFT = {
    '\u0e48': '\uf713', '\u0e49': '\uf714', '\u0e4a': '\uf715', '\u0e4b': '\uf716', '\u0e4c': '\uf717'
}

_LOWER_VOWEL = set('\u0e38\u0e39\u0e3a')
_LOWER_VOWEL_LOW = {'\u0e38': '\uf718', '\u0e39': '\uf719', '\u0e3a': '\uf71a'}

_PUA_TO_THAI = {
    '\uf700': '\u0e10',
    '\uf701': '\u0e34', '\uf702': '\u0e35', '\uf703': '\u0e36', '\uf704': '\u0e37',
    '\uf705': '\u0e48', '\uf706': '\u0e49', '\uf707': '\u0e4a', '\uf708': '\u0e4b', '\uf709': '\u0e4c',
    '\uf70a': '\u0e48', '\uf70b': '\u0e49', '\uf70c': '\u0e4a', '\uf70d': '\u0e4b', '\uf70e': '\u0e4c',
    '\uf70f': '\u0e0d',
    '\uf710': '\u0e31', '\uf711': '\u0e4d', '\uf712': '\u0e47',
    '\uf713': '\u0e48', '\uf714': '\u0e49', '\uf715': '\u0e4a', '\uf716': '\u0e4b', '\uf717': '\u0e4c',
    '\uf718': '\u0e38', '\uf719': '\u0e39', '\uf71a': '\u0e3a',
}


def adjust_thai(text: str) -> str:
    """ปรับวรรณยุกต์และสระภาษาไทยให้อยู่ในตำแหน่งที่ถูกต้อง (PUA) ไม่ซ้อนทับกัน"""
    if not text:
        return ''
    text = str(text).replace('\u2192', '->').replace('\u2194', '<->').replace('\u2190', '<-')
    chars = list(text)
    n = len(chars)
    out: list[str] = []
    prev_cons = ''
    i = 0
    while i < n:
        c = chars[i]
        # สระอำ (ำ) ที่มีวรรณยุกต์นำหน้า (เช่น น้ำ, ย้ำ, ค่ำ, ถ้ำ)
        if c in _TONE and i + 1 < n and chars[i + 1] == '\u0e33':
            out.append(_TONE_UP[c])
            i += 1
            continue

        # กรณีลำดับสลับ: วรรณยุกต์มาก่อนสระบน ให้สลับสระบนขึ้นก่อนและยกวรรณยุกต์ไปชั้นบน (Level 2)
        if c in _TONE and i + 1 < n and chars[i + 1] in _UPPER_VOWEL:
            upper = chars[i + 1]
            has_asc = prev_cons in _ASCENDER
            out.append(_UPPER_VOWEL_LEFT.get(upper, upper) if has_asc else upper)
            out.append(_TONE_UP[c])
            i += 2
            continue

        # สระบน (ิ, ี, ึ, ื, ั, ็, ํ)
        if c in _UPPER_VOWEL:
            has_asc = prev_cons in _ASCENDER
            out.append(_UPPER_VOWEL_LEFT.get(c, c) if has_asc else c)
            # ตรวจสอบว่ามีวรรณยุกต์ซ้อนด้านบนหรือไม่ (เช่น สิ่ง, ที่, ซึ่ง, ขึ้น, หนึ่ง, ลิขสิทธิ์)
            if i + 1 < n and chars[i + 1] in _TONE:
                tone = chars[i + 1]
                out.append(_TONE_UP[tone])
                i += 2
                continue
            i += 1
            continue

        # วรรณยุกต์เดี่ยวบนพยัญชนะ (เช่น ป่า, ป้า, ฟ้า -> หลบหางพยัญชนะมีหาง)
        if c in _TONE:
            has_asc = prev_cons in _ASCENDER
            out.append(_TONE_LEFT[c] if has_asc else c)
            i += 1
            continue

        # สระล่าง (ุ, ู, ฺ)
        if c in _LOWER_VOWEL:
            has_desc = prev_cons in _DESCENDER
            out.append(_LOWER_VOWEL_LOW[c] if has_desc else c)
            i += 1
            continue

        # ญ, ฐ ที่มีสระล่างรองรับ (ตัดเชิงออกไม่ให้ทับสระล่าง)
        if c in _PEDESTAL and i + 1 < n and chars[i + 1] in _LOWER_VOWEL:
            out.append(_PEDESTAL[c])
            i += 1
            continue

        out.append(c)
        if '\u0e01' <= c <= '\u0e2e':
            prev_cons = c
        elif c in ' \t\n\r':
            prev_cons = ''
        i += 1
    return ''.join(out)


def unshape_thai(text: str) -> str:
    """แปลงอักขระ PUA กลับเป็นอักขระภาษาไทยมาตรฐาน"""
    if not text:
        return ''
    return ''.join(_PUA_TO_THAI.get(c, c) for c in str(text))


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
        return pdfmetrics.stringWidth(adjust_thai(text), font, size)
    except Exception:
        return len(text) * size * 0.55


def wrap(text: str, size: float, max_width: float, bold: bool = False,
         max_lines: int = 99) -> list[str]:
    """ตัดบรรทัดตามคำภาษาไทยอย่างแม่นยำ ไม่ให้คำขาดกลาง (pythainlp tokenization)"""
    if not text:
        return ['']
    try:
        import pythainlp
        # ตัดข้อความตามคำจริง
        unshaped = unshape_thai(text)
        tokens = pythainlp.word_tokenize(unshaped, engine='newmm', keep_whitespace=True)
    except Exception:
        tokens = list(text)

    lines: list[str] = []
    current_tokens: list[str] = []
    current_w = 0.0

    for tok in tokens:
        if tok == '\n':
            lines.append(''.join(current_tokens))
            current_tokens = []
            current_w = 0.0
            continue
        tw = text_width(tok, size, bold)
        if current_w + tw <= max_width or not current_tokens:
            current_tokens.append(tok)
            current_w += tw
        else:
            lines.append(''.join(current_tokens))
            current_tokens = [tok]
            current_w = tw

    if current_tokens:
        lines.append(''.join(current_tokens))

    # ปรับตำแหน่งสระและวรรณยุกต์ในแต่ละบรรทัดให้สมบูรณ์
    shaped_lines = [adjust_thai(line.strip()) for line in lines]
    if len(shaped_lines) > max_lines:
        shaped_lines = shaped_lines[:max_lines]
        shaped_lines[-1] = shaped_lines[-1][:max(0, int(max_width / (size * 0.55)) - 1)] + '…'
    return shaped_lines

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
    """วางข้อความ 1 บรรทัด (รองรับจัดกึ่งกลาง/ขวา พร้อมจัดตำแหน่งสระไทย)"""
    val = adjust_thai(value)
    if align == 'center':
        x = x + width / 2 - text_width(val, size, bold) / 2
    elif align == 'right':
        x = x + width - text_width(val, size, bold)
    draw.add(String(x, y, val,
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
    draw.add(Circle(x, y + 26, 9, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.3))
    # ลำตัว
    draw.add(Line(x, y + 17, x, y - 8, strokeColor=LINE, strokeWidth=1.3))
    # แขน
    draw.add(Line(x - 16, y + 6, x + 16, y + 6, strokeColor=LINE, strokeWidth=1.3))
    # ขาซ้ายและขาขวา
    draw.add(Line(x, y - 8, x - 11, y - 26, strokeColor=LINE, strokeWidth=1.3))
    draw.add(Line(x, y - 8, x + 11, y - 26, strokeColor=LINE, strokeWidth=1.3))
    # ป้ายกำกับ
    text(draw, x, y - 38, label, 11, INK, bold=True, align='center')
    if sublabel:
        text(draw, x, y - 50, sublabel, 9.5, INK, align='center')


def usecase_oval(draw: Drawing, cx: float, cy: float, w: float, h: float,
                 label: str, code: str = '') -> None:
    """วาด Use Case รูปวงรี/ขอบมนตามมาตรฐาน UML"""
    draw.add(Rect(cx - w / 2, cy - h / 2, w, h, rx=h / 2, ry=h / 2,
                  fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    if code:
        text(draw, cx, cy + 5, code, 9.0, INK, bold=True, align='center')
        text(draw, cx, cy - 8, label, 9.5, INK, bold=False, align='center')
    else:
        text(draw, cx, cy - 3, label, 9.5, INK, bold=False, align='center')


# ---------------------------------------------------------------------------
# ไดอะแกรม 1: Use Case Diagram (มาตรฐาน UML)
# ---------------------------------------------------------------------------
def use_case_diagram(cases: dict[str, list[tuple[str, str]]] | None = None,
                     title: str = 'Use Case Diagram') -> Drawing:
    """แผนภาพกรณีการใช้งานตามมาตรฐาน UML (Use Case Diagram)"""
    width = 440
    height = 390
    d = Drawing(width, height)

    # 1. ขอบเขตระบบ (System Boundary)
    sys_x, sys_y, sys_w, sys_h = 74, 15, 292, 360
    d.add(Rect(sys_x, sys_y, sys_w, sys_h, rx=4, ry=4,
               fillColor=PAPER, strokeColor=LINE, strokeWidth=1.2))
    text(d, sys_x + 12, sys_y + sys_h - 18,
         'ระบบร้านค้าออนไลน์ THAMMATHAD SHOP (System Boundary)', 10.5, INK, bold=True)

    # 2. ผู้กระทำ (Actors)
    cust_x, cust_y = 36, 195
    actor_figure(d, cust_x, cust_y, 'ลูกค้า', '(Customer)')

    staff_x, staff_y = 404, 195
    actor_figure(d, staff_x, staff_y, 'เจ้าหน้าที่', '(Staff / Admin)')

    # 3. Use Cases
    customer_cases = [
        ('UC-01', 'สืบค้นแคตตาล็อกสินค้า', 310),
        ('UC-02', 'จัดการตะกร้าและสั่งซื้อ', 248),
        ('UC-03', 'ชำระเงินและแจ้งโอน', 186),
        ('UC-04', 'ติดตามและยืนยันรับของ', 124),
        ('UC-05', 'จัดการข้อมูลส่วนตัว/ที่อยู่', 62),
    ]

    staff_cases = [
        ('UC-06', 'จัดการสินค้าและสต็อก', 310),
        ('UC-07', 'ตรวจสอบยอดชำระเงิน', 248),
        ('UC-08', 'จัดการสถานะจัดส่งพัสดุ', 186),
        ('UC-09', 'ตรวจสอบบันทึกการทำงาน', 124),
        ('UC-10', 'จัดการสิทธิ์พนักงาน', 62),
    ]

    col1_cx = sys_x + 72
    col2_cx = sys_x + sys_w - 72
    ow, oh = 126, 42

    for code, label, cy in customer_cases:
        usecase_oval(d, col1_cx, cy, ow, oh, label, code)
        d.add(Line(cust_x + 18, cust_y, col1_cx - ow / 2, cy,
                   strokeColor=LINE, strokeWidth=0.8))

    for code, label, cy in staff_cases:
        usecase_oval(d, col2_cx, cy, ow, oh, label, code)
        d.add(Line(staff_x - 18, staff_y, col2_cx + ow / 2, cy,
                   strokeColor=LINE, strokeWidth=0.8))

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 2: สถาปัตยกรรมแบบ 4 ชั้น (4-Layer System Architecture)
# ---------------------------------------------------------------------------
def layered_architecture() -> Drawing:
    """แผนภาพสถาปัตยกรรมระบบแบบ 4 ชั้น (Layered Architecture) เชิงวิชาการ"""
    w, h = 440, 360
    d = Drawing(w, h)

    layers = [
        ('1. ชั้นนำเสนอ (Presentation Layer)',
         'เว็บแอปพลิเคชัน: HTML5, Apple Liquid Glass CSS, Motion Core JS\nส่วนบริการ REST API: Django REST Framework (Public & Staff Endpoints)'),
        ('2. ชั้นควบคุมและตรรกะมุมมอง (View & Controller Layer)',
         'Django Class-Based Views (CBVs) · สิทธิ์การเข้าถึง (StaffRequiredMixin, RBAC)\nการควบคุมความถี่และจำกัดอัตราเรียกใช้ (Rate Limiting & Token Throttling)'),
        ('3. ชั้นบริการทางธุรกิจ (Business Service Layer)',
         'PaymentService (จุดรับเงินจุดเดียว) · OrderStatusService (เครื่องจักรสถานะ 4 ขั้น)\nAudit Trail Logging · SlipOK OCR Verification · PromptPay QR Generation'),
        ('4. ชั้นการเข้าถึงและจัดเก็บข้อมูล (Data Access & Persistence Layer)',
         'Django Object-Relational Mapping (ORM) · Custom QuerySets & Managers\nฐานข้อมูลเชิงสัมพันธ์ SQLite พร้อมระบบสำรองข้อมูล (Automated Backups)'),
    ]

    box_w, box_h = 420, 60
    box_x = 10
    gap = 14
    y = h - 18

    for i, (title_text, desc_text) in enumerate(layers):
        cur_y = y - box_h
        # กล่องหลัก
        d.add(Rect(box_x, cur_y, box_w, box_h, rx=3, ry=3,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
        # แถบหัวข้อ
        d.add(Rect(box_x, cur_y + box_h - 22, box_w, 22, rx=3, ry=3,
                   fillColor=HexColor('#f0f0f0'), strokeColor=LINE, strokeWidth=0.8))
        text(d, box_x + 10, cur_y + box_h - 15, title_text, 11, INK, bold=True)

        # รายละเอียด 2 บรรทัด
        lines = desc_text.split('\n')
        text(d, box_x + 12, cur_y + 24, lines[0], 9.5, INK)
        text(d, box_x + 12, cur_y + 9, lines[1], 9.5, INK)

        if i < len(layers) - 1:
            arrow(d, box_x + box_w / 2, cur_y, box_x + box_w / 2, cur_y - gap,
                  color=INK, width=1.2, head=5.5)

        y -= box_h + gap

    # หมายเหตุ
    note(d, box_x, 6, box_w,
         'หลักการออกแบบ: รวมศูนย์ตรรกะทางธุรกิจไว้ที่ชั้น Service (Single Source of Truth) เพื่อความปลอดภัยและความคงสภาพของข้อมูล',
         fill=PAPER, stroke=LINE, color=INK, size=9.0)

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 3: แผนภาพการเปลี่ยนสถานะของคำสั่งซื้อ (Order State Machine)
# ---------------------------------------------------------------------------
def order_lifecycle_diagram(statuses: list[tuple[str, str]] | None = None,
                            actors: list[str] | None = None) -> Drawing:
    """แผนภาพการเปลี่ยนสถานะคำสั่งซื้อตามมาตรฐาน UML State Transition"""
    w, h = 440, 275
    d = Drawing(w, h)

    main_y = 185
    sw, sh = 72, 44
    gap = 36

    # 1. Initial State
    d.add(Circle(12, main_y, 6, fillColor=INK, strokeColor=None))
    arrow(d, 18, main_y, 28, main_y, color=INK, width=1.0)
    text(d, 23, main_y + 10, 'สั่งซื้อ', 8.0, INK, bold=True, align='center')

    sx1 = 28
    sx2 = sx1 + sw + gap
    sx3 = sx2 + sw + gap
    sx4 = sx3 + sw + gap

    steps = [
        ('รอชำระเงิน', '[PENDING]', sx1),
        ('ชำระเงินแล้ว', '[PAID]', sx2),
        ('จัดส่งแล้ว', '[SHIPPED]', sx3),
        ('ถึงมือแล้ว', '[DELIVERED]', sx4),
    ]

    for label, code, sx in steps:
        d.add(Rect(sx, main_y - sh / 2, sw, sh, rx=3, ry=3,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
        text(d, sx + sw / 2, main_y + 4, label, 10, INK, bold=True, align='center')
        text(d, sx + sw / 2, main_y - 10, code, 8.5, INK, align='center')

    # Transitions
    def draw_trans(from_x: float, to_x: float, title_text: str, sub_text: str):
        arrow(d, from_x, main_y, to_x, main_y, color=INK, width=1.0)
        cx = (from_x + to_x) / 2
        text(d, cx, main_y + 11, title_text, 8.5, INK, bold=True, align='center')
        text(d, cx, main_y - 12, sub_text, 8.0, INK, align='center')

    draw_trans(sx1 + sw, sx2, 'ชำระเงินครบ', 'จุดรับเงินเดียว')
    draw_trans(sx2 + sw, sx3, 'จัดส่งพัสดุ', 'เจ้าหน้าที่คลัง')
    draw_trans(sx3 + sw, sx4, 'ยืนยันรับของ', 'ลูกค้าเป็นหลัก')

    # Final state
    fin_x = sx4 + sw + 24
    arrow(d, sx4 + sw, main_y, fin_x - 8, main_y, color=INK, width=1.0)
    d.add(Circle(fin_x, main_y, 7, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    d.add(Circle(fin_x, main_y, 4, fillColor=INK, strokeColor=None))
    text(d, fin_x, main_y - 18, 'เสร็จสมบูรณ์', 8.5, INK, align='center')

    # Superuser Override
    arch_y = main_y + 40
    cx_s1, cx_s2 = sx1 + sw / 2, sx2 + sw / 2
    l1 = Line(cx_s1, main_y + sh / 2, cx_s1, arch_y, strokeColor=LINE, strokeWidth=0.8)
    l1.strokeDashArray = [3, 2]
    d.add(l1)
    l2 = Line(cx_s1, arch_y, cx_s2, arch_y, strokeColor=LINE, strokeWidth=0.8)
    l2.strokeDashArray = [3, 2]
    d.add(l2)
    arrow(d, cx_s2, arch_y, cx_s2, main_y + sh / 2, color=INK, width=0.8, dashed=True)
    text(d, (cx_s1 + cx_s2) / 2, arch_y + 4, 'Superuser Override (ระบุเหตุผล/เงินสดหน้าร้าน)', 8.5, INK, bold=True, align='center')

    # Cancelled branch
    canc_x, canc_y = sx1, 75
    arrow(d, sx1 + sw / 2, main_y - sh / 2, sx1 + sw / 2, canc_y + sh / 2,
          color=INK, width=1.0)
    text(d, sx1 + sw / 2 + 6, (main_y + canc_y) / 2 - 2, 'ลูกค้ายกเลิก', 8.5, INK)

    d.add(Rect(canc_x, canc_y - sh / 2, sw, sh, rx=3, ry=3,
               fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    text(d, canc_x + sw / 2, canc_y + 4, 'ยกเลิกคำสั่งซื้อ', 10, INK, bold=True, align='center')
    text(d, canc_x + sw / 2, canc_y - 10, '[CANCELLED]', 8.5, INK, align='center')

    fin2_x = canc_x + sw + 35
    arrow(d, canc_x + sw, canc_y, fin2_x - 8, canc_y, color=INK, width=1.0)
    d.add(Circle(fin2_x, canc_y, 7, fillColor=PAPER, strokeColor=LINE, strokeWidth=1.0))
    d.add(Circle(fin2_x, canc_y, 4, fillColor=INK, strokeColor=None))
    text(d, fin2_x, canc_y - 18, 'ยุติคำสั่งซื้อ', 8.5, INK, align='center')

    # Note
    note(d, 8, 8, w - 16,
         'กฎเกณฑ์ความคงสภาพ (Invariants): การเปลี่ยนสถานะเป็นไปตามบันไดทางเดียว ห้ามข้ามขั้นตอนและห้ามย้อนกลับ '
         'สถานะ PAID เกิดขึ้นอัตโนมัติเมื่อชำระครบถ้วนผ่าน PaymentService เท่านั้น',
         fill=PAPER, stroke=LINE, color=INK, size=8.8)

    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 4: แผนภาพแบบจำลองข้อมูลเชิงสัมพันธ์ (Relational Schema / ERD)
# ---------------------------------------------------------------------------
def er_diagram(models: Iterable | None = None, title: str = 'ER Diagram') -> Drawing:
    """แผนภาพแบบจำลองข้อมูลเชิงสัมพันธ์ (Relational Schema Diagram / ERD) ตามมาตรฐานวิชาการ

    รูปแบบมาตรฐานสากล:
    - รูปแบบกล่อง: แยกช่อง Primary Key (PK) ด้วยเส้นแบ่งแนวนอนชัดเจนตามมาตรฐาน Crow's Foot / Martin Notation
    - รูปแบบความสัมพันธ์: ใช้สัญลักษณ์ตีนกา (Crow's Foot: 1, Exactly One = ||, Many = |<) ไม่มีหัวลูกศร
    - จัดวางแบบ 3 คอลัมน์ เส้นเชื่อมโยงตรงและเป็นระเบียบ ไม่ทับซ้อน
    """
    w, h = 440, 590
    d = Drawing(w, h)

    col_w = 118
    col1_x = 12
    col2_x = 161
    col3_x = 310

    def draw_erd_entity(x: float, y: float, w_box: float, title_text: str, subtitle: str,
                        pk_fields: list[tuple[str, str, str, str]],
                        other_fields: list[tuple[str, str, str, str]]) -> tuple[float, float, float, float]:
        line_h = 13.0
        hdr_h = 22
        pk_h = len(pk_fields) * line_h + 4
        other_h = len(other_fields) * line_h + 4
        box_h = hdr_h + pk_h + other_h

        # เส้นขอบกล่องแบบมุมฉากมาตรฐานวิศวกรรมฐานข้อมูล
        d.add(Rect(x, y, w_box, box_h, rx=0, ry=0,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1.1))

        # แถบหัวชื่อเอนทิตี (Entity Header)
        d.add(Rect(x, y + box_h - hdr_h, w_box, hdr_h, rx=0, ry=0,
                   fillColor=HexColor('#e8e8e8'), strokeColor=LINE, strokeWidth=0.9))
        text(d, x + 6, y + box_h - 15, title_text, 9.5, INK, bold=True)
        if subtitle:
            text(d, x + w_box - 6, y + box_h - 15, subtitle, 8.5, INK, align='right')

        # ช่องคีย์หลัก (Primary Key Compartment)
        cur_y = y + box_h - hdr_h
        for i, (prefix, name, ftype, note_str) in enumerate(pk_fields):
            fy = cur_y - 12 - i * line_h
            text(d, x + 5, fy, prefix, 8.5, INK, bold=True)
            text(d, x + 24, fy, f'{name} : {ftype}' if ftype else name, 8.5, INK, bold=True)
            if note_str:
                text(d, x + w_box - 5, fy, note_str, 7.5, INK, align='right')

        # เส้นแบ่งระหว่าง Primary Key กับแอตทริบิวต์ทั่วไป (ERD Compartment Divider)
        sep_y = cur_y - pk_h
        d.add(Line(x, sep_y, x + w_box, sep_y, strokeColor=LINE, strokeWidth=1.0))

        # ช่องแอตทริบิวต์ทั่วไปและคีย์นอก (Attributes & Foreign Keys Compartment)
        for i, (prefix, name, ftype, note_str) in enumerate(other_fields):
            fy = sep_y - 12 - i * line_h
            is_fk = prefix == 'FK'
            text(d, x + 5, fy, prefix, 8.5, INK, bold=is_fk)
            text(d, x + 24, fy, f'{name} : {ftype}' if ftype else name, 8.5, INK, bold=is_fk)
            if note_str:
                text(d, x + w_box - 5, fy, note_str, 7.5, INK, align='right')

        return x, y, w_box, box_h

    # ฟังก์ชันวาดเส้นความสัมพันธ์สัญลักษณ์ตีนกา (Crow's Foot Notation Connectors)
    def cf_v(x: float, y1: float, y2: float, one_at_start: bool = True,
             many_at_end: bool = True, one_at_end: bool = False) -> None:
        """เส้นเชื่อมแนวตั้งพร้อมสัญลักษณ์ตีนกา"""
        dy = 1 if y2 >= y1 else -1
        d.add(Line(x, y1, x, y2, strokeColor=LINE, strokeWidth=1.0))

        # ฝั่งต้นทาง (One = ||)
        if one_at_start:
            d.add(Line(x - 5, y1 + dy * 5, x + 5, y1 + dy * 5, strokeColor=LINE, strokeWidth=1.1))
            d.add(Line(x - 5, y1 + dy * 9, x + 5, y1 + dy * 9, strokeColor=LINE, strokeWidth=1.1))

        # ฝั่งปลายทาง
        if many_at_end:
            # ตีนกา 3 แฉกแผ่เข้าหากรอบเอนทิตี
            base_y = y2 - dy * 9
            d.add(Line(x, base_y, x - 6, y2, strokeColor=LINE, strokeWidth=1.2))
            d.add(Line(x, base_y, x + 6, y2, strokeColor=LINE, strokeWidth=1.2))
            d.add(Line(x - 5, y2 - dy * 12, x + 5, y2 - dy * 12, strokeColor=LINE, strokeWidth=1.1))
        elif one_at_end:
            d.add(Line(x - 5, y2 - dy * 5, x + 5, y2 - dy * 5, strokeColor=LINE, strokeWidth=1.1))
            d.add(Line(x - 5, y2 - dy * 9, x + 5, y2 - dy * 9, strokeColor=LINE, strokeWidth=1.1))

    def cf_h(x1: float, x2: float, y: float, one_at_start: bool = True,
             many_at_end: bool = True, one_at_end: bool = False) -> None:
        """เส้นเชื่อมแนวนอนพร้อมสัญลักษณ์ตีนกา"""
        dx = 1 if x2 >= x1 else -1
        d.add(Line(x1, y, x2, y, strokeColor=LINE, strokeWidth=1.0))

        # ฝั่งต้นทาง (One = ||)
        if one_at_start:
            d.add(Line(x1 + dx * 5, y - 5, x1 + dx * 5, y + 5, strokeColor=LINE, strokeWidth=1.1))
            d.add(Line(x1 + dx * 9, y - 5, x1 + dx * 9, y + 5, strokeColor=LINE, strokeWidth=1.1))

        # ฝั่งปลายทาง
        if many_at_end:
            # ตีนกา 3 แฉกแผ่เข้าหากรอบเอนทิตี
            base_x = x2 - dx * 9
            d.add(Line(base_x, y, x2, y + 6, strokeColor=LINE, strokeWidth=1.2))
            d.add(Line(base_x, y, x2, y - 6, strokeColor=LINE, strokeWidth=1.2))
            d.add(Line(x2 - dx * 12, y - 5, x2 - dx * 12, y + 5, strokeColor=LINE, strokeWidth=1.1))
        elif one_at_end:
            d.add(Line(x2 - dx * 5, y - 5, x2 - dx * 5, y + 5, strokeColor=LINE, strokeWidth=1.1))
            d.add(Line(x2 - dx * 9, y - 5, x2 - dx * 9, y + 5, strokeColor=LINE, strokeWidth=1.1))

    boxes: dict[str, tuple[float, float, float, float]] = {}

    # แถวที่ 1 (ด้านบน)
    boxes['CustomerProfile'] = draw_erd_entity(col1_x, 465, col_w, 'CustomerProfile', '(โปรไฟล์)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'user_id', 'integer', '1:1'),
         ('', 'phone', 'varchar(20)', ''),
         ('', 'bio', 'text', '')]
    )
    boxes['OrderIssue'] = draw_erd_entity(col2_x, 452, col_w, 'OrderIssue', '(แจ้งปัญหา)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'order_id', 'bigint', 'N:1'),
         ('FK', 'user_id', 'integer', 'N:1'),
         ('', 'category', 'varchar(20)', ''),
         ('', 'status', 'varchar(20)', '')]
    )
    boxes['Product'] = draw_erd_entity(col3_x, 438, col_w, 'Product', '(สินค้า/สต็อก)',
        [('PK', 'id', 'integer', '')],
        [('', 'sku', 'varchar(32)', 'UQ'),
         ('', 'name', 'varchar(200)', ''),
         ('', 'category', 'varchar(50)', ''),
         ('', 'price', 'decimal(10,2)', ''),
         ('', 'stock', 'integer', '')]
    )

    # แถวที่ 2 (แถวกลาง: แกนหลักของระบบ)
    boxes['User'] = draw_erd_entity(col1_x, 275, col_w, 'User (auth_user)', '(ผู้ใช้หลัก)',
        [('PK', 'id', 'integer', '')],
        [('', 'username', 'varchar', 'UQ'),
         ('', 'email', 'varchar(254)', ''),
         ('', 'is_staff', 'boolean', ''),
         ('', 'is_active', 'boolean', '')]
    )
    boxes['Order'] = draw_erd_entity(col2_x, 245, col_w, 'Order', '(คำสั่งซื้อ)',
        [('PK', 'id', 'integer', '')],
        [('', 'order_number', 'varchar', 'UQ'),
         ('FK', 'user_id', 'integer', 'N:1'),
         ('', 'total', 'decimal(10,2)', ''),
         ('', 'status', 'varchar(20)', ''),
         ('', 'payment_method', 'str', ''),
         ('', 'created_at', 'datetime', '')]
    )
    boxes['OrderItem'] = draw_erd_entity(col3_x, 260, col_w, 'OrderItem', '(รายการสั่ง)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'order_id', 'bigint', 'N:1'),
         ('FK', 'product_id', 'bigint', 'N:1'),
         ('', 'price', 'decimal(10,2)', ''),
         ('', 'quantity', 'integer', ''),
         ('', 'line_total', 'decimal', '')]
    )

    # แถวที่ 3 (ด้านล่าง)
    boxes['CustomerAddress'] = draw_erd_entity(col1_x, 115, col_w, 'CustomerAddress', '(ที่อยู่)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'user_id', 'integer', 'N:1'),
         ('', 'recipient_name', 'varchar', ''),
         ('', 'phone', 'varchar(20)', ''),
         ('', 'province', 'varchar(50)', ''),
         ('', 'is_default', 'boolean', '')]
    )
    boxes['Payment'] = draw_erd_entity(col2_x, 115, col_w, 'Payment', '(การชำระเงิน)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'order_id', 'bigint', 'N:1'),
         ('', 'amount', 'decimal(10,2)', ''),
         ('', 'channel', 'varchar(20)', ''),
         ('', 'is_approved', 'boolean', ''),
         ('', 'paid_at', 'datetime', '')]
    )
    boxes['Employee'] = draw_erd_entity(col3_x, 115, col_w, 'Employee', '(พนักงาน)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'user_id', 'integer', '1:1'),
         ('', 'emp_code', 'varchar(20)', 'UQ'),
         ('', 'name', 'varchar(100)', ''),
         ('', 'department', 'varchar', ''),
         ('', 'salary', 'decimal(10,2)', ''),
         ('', 'status', 'varchar(20)', '')]
    )

    # แถวที่ 4 (แถวล่างสุด: ActivityLog)
    boxes['ActivityLog'] = draw_erd_entity(50, 18, 340, 'ActivityLog (Audit Trail)', '(ประวัติกิจกรรม - Append Only)',
        [('PK', 'id', 'integer', '')],
        [('FK', 'actor_id', 'integer', 'N:1 User (SET_NULL)'),
         ('', 'action : varchar(20)         target_model : varchar(50)         created_at : datetime', '', '')]
    )

    # ความสัมพันธ์แบบ Crow's Foot:
    # 1. User (1) -> CustomerProfile (1): Vertical 1:1
    cf_v(col1_x + 59, 275 + boxes['User'][3], 465, one_at_start=True, many_at_end=False, one_at_end=True)
    text(d, col1_x + 65, (275 + boxes['User'][3] + 465) / 2 - 3, '1:1', 8.5, INK, bold=True)

    # 2. User (1) -> CustomerAddress (N): Vertical 1:N
    cf_v(col1_x + 59, 275, 115 + boxes['CustomerAddress'][3], one_at_start=True, many_at_end=True)
    text(d, col1_x + 65, (275 + 115 + boxes['CustomerAddress'][3]) / 2 - 3, '1:N', 8.5, INK, bold=True)

    # 3. User (1) -> Order (N): Horizontal 1:N
    cf_h(col1_x + col_w, col2_x, 300, one_at_start=True, many_at_end=True)
    text(d, (col1_x + col_w + col2_x) / 2, 306, '1:N', 8.5, INK, bold=True, align='center')

    # 4. Order (1) -> OrderIssue (N): Vertical 1:N
    cf_v(col2_x + 59, 245 + boxes['Order'][3], 452, one_at_start=True, many_at_end=True)
    text(d, col2_x + 65, (245 + boxes['Order'][3] + 452) / 2 - 3, '1:N', 8.5, INK, bold=True)

    # 5. Order (1) -> Payment (N): Vertical 1:N
    cf_v(col2_x + 59, 245, 115 + boxes['Payment'][3], one_at_start=True, many_at_end=True)
    text(d, col2_x + 65, (245 + 115 + boxes['Payment'][3]) / 2 - 3, '1:N', 8.5, INK, bold=True)

    # 6. Order (1) -> OrderItem (N): Horizontal 1:N
    cf_h(col2_x + col_w, col3_x, 290, one_at_start=True, many_at_end=True)
    text(d, (col2_x + col_w + col3_x) / 2, 296, '1:N', 8.5, INK, bold=True, align='center')

    # 7. Product (1) -> OrderItem (N): Vertical 1:N
    cf_v(col3_x + 59, 438, 260 + boxes['OrderItem'][3], one_at_start=True, many_at_end=True)
    text(d, col3_x + 65, (438 + 260 + boxes['OrderItem'][3]) / 2 - 3, '1:N', 8.5, INK, bold=True)

    # 8. User (1) -> ActivityLog (N): Orthogonal stepped
    d.add(Line(col1_x, 290, 4, 290, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(col1_x - 5, 290 - 5, col1_x - 5, 290 + 5, strokeColor=LINE, strokeWidth=1.1))
    d.add(Line(col1_x - 9, 290 - 5, col1_x - 9, 290 + 5, strokeColor=LINE, strokeWidth=1.1))

    d.add(Line(4, 290, 4, 36, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(4, 36, 50, 36, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(41, 36, 50, 36 + 6, strokeColor=LINE, strokeWidth=1.2))
    d.add(Line(41, 36, 50, 36 - 6, strokeColor=LINE, strokeWidth=1.2))
    d.add(Line(38, 36 - 5, 38, 36 + 5, strokeColor=LINE, strokeWidth=1.1))
    text(d, 26, 41, '1:N', 8.0, INK, bold=True, align='center')

    # 9. User (1) -> Employee (1): Stepped 1:1 via alley and lower channel
    # ฝั่งต้นทาง User (Exactly One = ||)
    d.add(Line(col1_x + col_w, 282, 145, 282, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(col1_x + col_w + 5, 282 - 5, col1_x + col_w + 5, 282 + 5, strokeColor=LINE, strokeWidth=1.1))
    d.add(Line(col1_x + col_w + 9, 282 - 5, col1_x + col_w + 9, 282 + 5, strokeColor=LINE, strokeWidth=1.1))

    # ลากลงผ่านช่องว่างระหว่าง Col 1 กับ Col 2 (x=145 ว่างสมบูรณ์)
    d.add(Line(145, 282, 145, 98, strokeColor=LINE, strokeWidth=1.0))

    # ลากแนวนอนใต้แถวที่ 3 (y=98 อยู่เหนือ ActivityLog และใต้ Employee)
    d.add(Line(145, 98, col3_x + 59, 98, strokeColor=LINE, strokeWidth=1.0))
    text(d, 245, 102, '1:1 (user_id)', 8.5, INK, bold=True, align='center')

    # ลากขึ้นเข้าสู่ฐานล่างของ Employee (Exactly One = ||)
    d.add(Line(col3_x + 59, 98, col3_x + 59, 115, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(col3_x + 59 - 5, 115 - 5, col3_x + 59 + 5, 115 - 5, strokeColor=LINE, strokeWidth=1.1))
    d.add(Line(col3_x + 59 - 5, 115 - 9, col3_x + 59 + 5, 115 - 9, strokeColor=LINE, strokeWidth=1.1))

    # คำอธิบายสัญลักษณ์ตามมาตรฐานวิชาการ (Standard ERD Crow's Foot Legend)
    ly = 4
    text(d, 10, ly, 'สัญลักษณ์ ERD:', 8.5, INK, bold=True)

    # ตัวอย่างเส้น 1 (Exactly One)
    d.add(Line(78, ly + 3, 108, ly + 3, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(93, ly - 2, 93, ly + 8, strokeColor=LINE, strokeWidth=1.1))
    d.add(Line(98, ly - 2, 98, ly + 8, strokeColor=LINE, strokeWidth=1.1))
    text(d, 113, ly, '= หนึ่ง (1)', 8.5, INK)

    # ตัวอย่างเส้น N (Many)
    d.add(Line(175, ly + 3, 205, ly + 3, strokeColor=LINE, strokeWidth=1.0))
    d.add(Line(193, ly - 2, 193, ly + 8, strokeColor=LINE, strokeWidth=1.1))
    d.add(Line(196, ly + 3, 205, ly + 9, strokeColor=LINE, strokeWidth=1.2))
    d.add(Line(196, ly + 3, 205, ly - 3, strokeColor=LINE, strokeWidth=1.2))
    text(d, 210, ly, '= หลายรายการ (N / Many)', 8.5, INK)

    # ป้ายกำกับคีย์
    text(d, 335, ly, '[PK] = คีย์หลัก     [FK] = คีย์นอก', 8.5, INK, bold=True)

    return d
"""วาดไดอะแกรมเป็น `reportlab.graphics.shapes.Drawing`

ทำไมวาดด้วย reportlab โดยตรง ไม่ผ่าน SVG
    ทดลองเส้นทาง SVG แล้ว (svglib) — svglib จับคู่ `font-family` กับฟอนต์ของ
    ตัวเอง ไม่ใช่ฟอนต์ที่ register ไว้ใน reportlab → **ภาษาไทยออกมาเป็น
    กล่องสีดำ** ทั้งที่ PDF ฝั่งอื่นใช้ฟอนต์ถูกต้อง

    วาดด้วย shapes ตรง ๆ แล้วส่งออกทั้ง PDF (vector) และ PNG (สำหรับฝังใน
    Word) ด้วย **ฟอนต์ชุดเดียวกัน** จึงไม่มีทางหลุดได้ — และไม่ต้องติดตั้ง
    cairosvg หรือโปรแกรมอื่นเพิ่ม

ข้อควรระวัง
    - ฟอนต์ Leelawadee ไม่มีอักขระลูกศร `→` → ต้องวาดเป็นเส้นจริงเสมอ
      (ดู `arrow()`)
    - ทุกฟังก์ชันคืนค่าเป็น Drawing ที่ยังไม่บันทึก เพื่อให้ผู้เรียกเลือกได้ว่าจะ
      ส่งออกเป็น PDF หรือ PNG
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
#: ตัวเลือกฟอนต์ที่รองรับภาษาไทย เรียงตามความสวยงามของตัวอักษร
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
    """ลงทะเบียนฟอนต์ไทยกับ reportlab — เรียกซ้ำได้ ไม่มีผลซ้ำ

    ค้นหาฟอนต์จากเครื่องจริงแทนการ hardcode เพราะชื่อไฟล์ฟอนต์ต่างกัน
    ระหว่าง Windows 10 / 11 / รุ่นเก่า และเครื่องของผู้เรียนอาจไม่มีชุดเดียวกัน

    Returns:
        (ชื่อฟอนต์ปกติ, ชื่อฟอนต์หนา)

    Raises:
        RuntimeError: ถ้าไม่พบฟอนต์ที่รองรับภาษาไทยเลย
    """
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
                TTFont(FONT_BOLD, bold if bold and os.path.exists(bold)
                       else regular))
            _font_ready = True
            return FONT_REGULAR, FONT_BOLD
        except Exception as exc:                      # ฟอนต์เสีย/ใช้ไม่ได้
            errors.append(f'{name}: {exc}')

    raise RuntimeError(
        'ไม่พบฟอนต์ที่รองรับภาษาไทยในเครื่องนี้\n'
        '  ต้องมีอย่างใดอย่างหนึ่ง: '
        + ', '.join(c[0] for c in THAI_FONT_CANDIDATES)
        + ('\n  ข้อผิดพลาด: ' + '; '.join(errors) if errors else '')
    )


def text_width(text: str, size: float, bold: bool = False) -> float:
    """ความกว้างของข้อความ — จำเป็นเพราะภาษาไทยไม่มีช่องว่างระหว่างคำ

    ถ้าคำนวณไม่ได้ (เช่น ฟอนต์ยังไม่ register) ให้ประมาณจากจำนวนอักขระ
    ดีกว่าล้มทั้งหมด เพราะความกว้างผิดนิดยังพอใช้ แต่โค้ดพังคือเอกสารไม่ออก
    """
    try:
        font = FONT_BOLD if bold else FONT_REGULAR
        return pdfmetrics.stringWidth(text, font, size)
    except Exception:
        return len(text) * size * 0.55


def wrap(text: str, size: float, max_width: float, bold: bool = False,
         max_lines: int = 99) -> list[str]:
    """ตัดบรรทัดตามความกว้างที่กำหนด

    ตัดตาม**อักขระ** ไม่ใช่ตามช่องว่าง เพราะภาษาไทยไม่มีช่องว่างระหว่างคำ
    การตัดตามช่องว่างจะทำให้ข้อความยาวตัวเดียวล้นกรอบ
    """
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
# สี — ยืมจากธีมเดียวกับหน้าเว็บ เพื่อให้เอกสารเข้ากับผลิตภัณฑ์
# ---------------------------------------------------------------------------
INK = HexColor('#14181f')
INK_SOFT = HexColor('#3d4552')
MUTED = HexColor('#6b7280')
LINE = HexColor('#c8ced8')
PAPER = HexColor('#ffffff')
BLUE = HexColor('#2b6cb0')
BLUE_SOFT = HexColor('#e8f2ff')
GREEN = HexColor('#1a7f52')
GREEN_SOFT = HexColor('#e6f5ed')
AMBER = HexColor('#9a6208')
AMBER_SOFT = HexColor('#fdf3e2')
RED = HexColor('#b4232b')
RED_SOFT = HexColor('#fdecec')
GREY_SOFT = HexColor('#f4f5f7')
PURPLE = HexColor('#5b3fa8')
PURPLE_SOFT = HexColor('#efeaf9')


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
          color: Color = INK_SOFT, width: float = 1.0,
          head: float = 5.0, dashed: bool = False) -> None:
    """วาดเส้นพร้อมหัวลูกศร

    ต้องวาดด้วยเส้นจริง เพราะฟอนต์ไทยบนเครื่องไม่มีอักขระ `→`
    (ถ้าใช้ตัวอักษรจะได้เป็นกล่องสีดำในเอกสารที่ส่งอาจารย์)
    """
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    # เว้นหัวลูกศรออกจากปลายเส้นเล็กน้อย กันเส้นทะลุหัว
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
    """กล่องหัวข้อ + คืนความสูงที่ใช้จริง (เผื่อข้อความหลายบรรทัด)"""
    sub_lines = wrap(subtitle, 7.2, w - 14) if subtitle else []
    h = max(h, 20 + len(sub_lines) * 9)
    draw.add(Rect(x, y, w, h, rx=5, ry=5,
                  fillColor=fill, strokeColor=stroke, strokeWidth=0.9))
    if accent:
        draw.add(Rect(x, y + 3, 3, h - 6, rx=1.5, ry=1.5,
                      fillColor=accent, strokeColor=None))
    text(draw, x + 9, y + h - 12, title, title_size, INK, bold=True)
    for i, line in enumerate(sub_lines):
        text(draw, x + 9, y + h - 22 - i * 9, line, 7.2, MUTED)
    return h


def note(draw: Drawing, x: float, y: float, w: float, msg: str,
         fill: Color = GREY_SOFT, stroke: Color = LINE,
         color: Color = INK_SOFT, size: float = 7.4) -> float:
    """กล่องหมายเหตุ — ใช้อธิบายเงื่อนไข/ข้อจำกัดของไดอะแกรม"""
    lines = wrap(msg, size, w - 16)
    h = 10 + len(lines) * 9.4
    draw.add(Rect(x, y, w, h, rx=4, ry=4,
                  fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
    for i, line in enumerate(lines):
        text(draw, x + 8, y + h - 12 - i * 9.4, line, size, color)
    return h


# ---------------------------------------------------------------------------
# ไดอะแกรม 1: ER Diagram
# ---------------------------------------------------------------------------
def er_diagram(models: Iterable, title: str = 'ER Diagram') -> Drawing:
    """ER Diagram แบบ Chen (กล่อง = ตาราง, เส้น = ความสัมพันธ์)

    อ่านข้อมูลจาก `facts.models_report()` จึงไม่มีทางตรงกับโค้ดไม่ตรงกัน
    """
    models = list(models)
    cols = 3
    gap_x, gap_v = 26, 26
    box_w = 168
    rows = (len(models) + cols - 1) // cols

    # ความสูงกล่องคำนวณจากจำนวนฟิลด์ที่จะแสดงจริง — กล่องสูงตายตัว
    # ทำให้ตารางที่มี 2 คอลัมน์ดูเหมือนมี 8 คอลัมน์ (พื้นที่ว่างกลืนสายตา)
    def _visible(m) -> list:
        return [f for f in m.fields
                if f.primary_key or f.is_fk
                or f.name in ('status', 'total', 'amount', 'kind',
                              'emp_code', 'name', 'product', 'price')][:4]

    heights = []
    for m in models:
        n = len(_visible(m))
        heights.append(30 + max(n, 1) * 11 + 8)

    # ทุกแถวใช้ความสูงเท่ากล่องที่สูงสุดในแถวนั้น จัดแนวกริดได้สวย
    row_h = [max(heights[r * cols:(r + 1) * cols] or [40]) for r in range(rows)]

    # กันที่ให้คำอธิบายสัญลักษณ์ + หมายเหตุท้ายภาพ
    # ต้องวัดความสูงจริงก่อน ไม่ใช่กำนดค่าคงที่ — ถ้ากำนดคงที่
    # แถวสุดท้ายจะทับกล่องหมายเหตุ (เคยเกิดแล้ว: กล่อง Product/Employee
    # ถูกหั่นกลางอยู่)
    local_names = {o.name for o in models}
    external = sorted({f.fk_target for m in models for f in m.fk_fields
                       if f.fk_target and f.fk_target not in local_names})
    note_text = (
        f'หมายเหตุ: ยังไม่แสดงความสัมพันธ์ไปยังตารางของ Django '
        f'({", ".join(external)}) เพราะอยู่นอกขอบเขตแอปนี้ — '
        'ในระบบจริง CustomerProfile / CustomerAddress / Order / ActivityLog '
        'ผูกกับผู้ใช้ 1 ราย เพื่อแยก "ลูกค้าสมาชิก" ออกจาก '
        '"ลูกค้าที่ไม่ได้สมัครสมาชิก"') if external else ''
    note_h = (10 + len(wrap(note_text, 6.8, width_of(columns=cols, box_w=box_w,
                                                     gap_x=gap_x) - 40)) * 9.4
              + 6) if note_text else 0

    width = cols * box_w + (cols - 1) * gap_x + 40
    legend_h = 22 if note_text else 0
    top_pad = 46
    height = sum(row_h) + (rows - 1) * gap_v + top_pad + legend_h + note_h + 14

    d = Drawing(width, height)
    text(d, 20, height - 22, title, 13, INK, bold=True)

    # จัดตำแหน่งและวาดกล่อง
    positions: dict[str, tuple[float, float, float]] = {}
    # y ของแต่ละแถวต้องทบสะสมจากแถวบนลงล่าง ถ้าใช้ค่าเดียวกันทุกแถว
    # กล่องทั้งหมดจะวางทับกันที่ตำแหน่งเดียว แล้วเห็นแค่แถวสุดท้าย
    row_top: list[float] = []
    cursor = height - top_pad
    for h in row_h:
        cursor -= h
        row_top.append(cursor)
        cursor -= gap_v

    for i, m in enumerate(models):
        col, row = i % cols, i // cols
        x = 20 + col * (box_w + gap_x)
        y = row_top[row]
        bh = row_h[row]
        positions[m.name] = (x, y, bh)

        d.add(Rect(x, y, box_w, bh, rx=6, ry=6,
                   fillColor=PAPER, strokeColor=LINE, strokeWidth=1))
        d.add(Rect(x, y + bh - 17, box_w, 17, rx=6, ry=6,
                   fillColor=BLUE_SOFT, strokeColor=None))
        d.add(Rect(x, y + bh - 17, box_w, 8,
                   fillColor=BLUE_SOFT, strokeColor=None))
        text(d, x + 9, y + bh - 12.5, m.name, 9, BLUE, bold=True)

        shown = _visible(m)
        for j, f in enumerate(shown):
            ty = y + bh - 30 - j * 11
            text(d, x + 9, ty, f'{f.name} : {f.short_type}', 6.8,
                 RED if f.is_fk else INK_SOFT, bold=f.primary_key)
        if len([f for f in m.fields
                if f.primary_key or f.is_fk
                or f.name in ('status', 'total', 'amount', 'kind',
                              'emp_code', 'name', 'product', 'price')]) > 4:
            text(d, x + 9, y + 5, '… ฟิลด์อื่น ๆ', 6.2, MUTED)

    # เส้นความสัมพันธ์
    drawn: set[tuple[str, str]] = set()
    for m in models:
        for f in m.fk_fields:
            target = next((o for o in models
                           if o.name in (f.fk_target or '')), None)
            if target is None or (target.name, m.name) in drawn:
                continue
            drawn.add((target.name, m.name))
            ax, ay = _edge_point(positions[target.name], positions[m.name],
                                 box_w, positions[target.name][2])
            bx, by = _edge_point(positions[m.name], positions[target.name],
                                 box_w, positions[m.name][2])
            arrow(d, ax, ay, bx, by, color=MUTED, width=0.9, dashed=True)

    # คำอธิบายสัญลักษณ์ + หมายเหตุ (วางต่ำกว่ากริด โดยใช้ความสูงที่วัดไว้แล้ว)
    ly = 8 + note_h + 4
    d.add(Circle(24, ly + 3, 3.2, fillColor=RED, strokeColor=None))
    text(d, 31, ly, 'PK = คีย์หลัก   ชื่อฟิลด์สีแดง = Foreign Key', 6.8, MUTED)
    arrow(d, 178, ly + 3, 202, ly + 3, color=MUTED, width=0.9, dashed=True)
    text(d, 206, ly, 'ความสัมพันธ์ FK (ลูกศรชี้จากตารางลูกไปยังตารางหลัก)', 6.8, MUTED)
    if note_text:
        note(d, 20, 8, width - 40, note_text,
             fill=GREY_SOFT, stroke=LINE, color=MUTED, size=6.8)

    return d


def width_of(columns: int, box_w: float, gap_x: float) -> float:
    """ความกว้างรวมของผืนภาพ คำนวณจากจำนวนคอลัมน์

    แยกเป็นฟังก์ชันเพราะต้องรู้ความกว้าง **ก่อน** คำนวณความสูงของกริด
    (เพื่อวัดความสูงกล่องหมายเหตุ) และเพื่อไม่ให้สูตรความกว้างซ้ำสองที่
    ซึ่งเคยทำให้ผืนภาพกับกล่องหมายเหตุไม่ตรงกัน
    """
    return columns * box_w + (columns - 1) * gap_x + 40


def _edge_point(frm: tuple[float, float], to: tuple[float, float],
                box_w: float, box_h: float) -> tuple[float, float]:
    """จุดบนขอบกล่อง `frm` ที่หันหน้าไปทางกล่อง `to`

    วาดจากกล่องหนึ่งไปอีกกล่อง โดยออกจาก **ขอบ** กล่องต้นทาง (ไม่ใช่กลาง)
    เพื่อไม่ให้เส้นทางผ่านเนื้อกล่อง แล้วจบที่กลางกล่องปลายทาง
    """
    x0, y0 = frm[0] + box_w / 2, frm[1] + box_h / 2
    x1, y1 = to[0] + box_w / 2, to[1] + box_h / 2
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return x0, y0
    tx = (box_w / 2) / abs(dx) if dx else float('inf')
    ty = (box_h / 2) / abs(dy) if dy else float('inf')
    # ห้าม cap ที่ 1.0: ค่าที่ถูกคือ "เดินไปถึงขอบกล่อง" ซึ่งมักน้อยกว่า 1
    # การ cap จะทำให้จุดตกกลางกล่อง → เส้นถูกกล่องทับจนมองไม่เห็น
    t = min(tx, ty)
    return x0 + dx * t, y0 + dy * t


# ---------------------------------------------------------------------------
# ไดอะแกรม 2: สถาปัตยกรรมแบบชั้น
# ---------------------------------------------------------------------------
def layered_architecture() -> Drawing:
    """แผนภาพสถาปัตยกรรมแบบ 3 ชั้นของระบบ

    วาดตามที่โค้ดจริงเป็น: URLs → Views (CBV) → Services → Models/DB
    """
    layers = [
        ('ชั้นนำเสนอ (Presentation)',
         'Template · Static (CSS/JS) · REST API (DRF)',
         BLUE, BLUE_SOFT),
        ('ชั้นตรรกะ (Views)',
         'Class-Based View ทั้งหมด · Mixin ควบคุมสิทธิ์',
         PURPLE, PURPLE_SOFT),
        ('ชั้นธุรกิจ (Service Layer)',
         'PaymentService · OrderStatusService · Audit · LoginThrottle',
         GREEN, GREEN_SOFT),
        ('ชั้นข้อมูล (Data)',
         'Model · QuerySet · Manager · SQLite',
         AMBER, AMBER_SOFT),
    ]
    note_text = ('หลักการสำคัญ: ตรรกะทางธุรกิจอยู่ที่ชั้น Service เท่านั้น View เรียกใช้ '
                 'เช่น "รับเงิน" มีจุดเดียวคือ PaymentService.record_payment() '
                 'ทุกช่องทาง (สลิป OCR / ปุ่มแจ้งยอด / กรอกเอง) เดินผ่านจุดนี้ '
                 'ไม่มีทางให้กติกาเงินสองชุดในระบบพร้อมกัน')

    box_w, box_h, gap = 400, 46, 16
    note_h = 10 + len(wrap(note_text, 7.4, 520 - 16)) * 9.4 + 12
    top_pad, bottom_pad = 52, note_h + 26

    # ความสูงต้องคำนวณจากทุกชิ้นรวมกัน ถ้ากำหนดค่าตายตัว
    # กล่องหมายเหตุจะทับชั้นล่าง (เคยเกิดกับชั้น "ข้อมูล")
    h = (top_pad + len(layers) * box_h + (len(layers) - 1) * gap
         + bottom_pad)
    w = 560

    d = Drawing(w, h)
    text(d, 20, h - 22, 'สถาปัตยกรรมแบบชั้น (Layered Architecture)', 12, INK,
         bold=True)

    y = h - top_pad
    for i, (name, detail, accent, fill) in enumerate(layers):
        d.add(Rect(20, y - box_h, box_w, box_h, rx=6, ry=6,
                   fillColor=fill, strokeColor=accent, strokeWidth=1))
        text(d, 34, y - 18, name, 10, accent, bold=True)
        text(d, 34, y - 33, detail, 7.6, INK_SOFT)
        if i < len(layers) - 1:
            arrow(d, 220, y - box_h - 2, 220, y - box_h - gap + 4,
                  color=MUTED, width=1.2)
        y -= box_h + gap

    # เส้นบอกทิศทางการเรียกจากบนลงล่าง
    arrow(d, 442, h - top_pad + 10, 442, y + 14, color=MUTED, width=1.2)
    text(d, 450, (h - top_pad + y) / 2 + 10, 'ทิศทางการเรียก', 7, MUTED)

    note(d, 20, 14, 520, note_text,
         fill=AMBER_SOFT, stroke=AMBER, color=AMBER, size=7.4)
    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 3: Sequence — วงจรชีวิตออเดอร์
# ---------------------------------------------------------------------------
def order_lifecycle_diagram(statuses: list[tuple[str, str]],
                            actors: list[str]) -> Drawing:
    """แผนผังลำดับการเปลี่ยนสถานะออเดอร์

    Args:
        statuses: [(ป้ายสถานะ, ผู้ทำให้เกิดการเปลี่ยนแปลง), ...] ตามลำดับ
        actors: ผู้เกี่ยวข้อง เช่น ['ลูกค้า', 'เจ้าหน้าที่', 'ระบบ']

    ตัวเลขใน statuses ถ้าต่างจากของจริง ไดอะแกรมจะเพี้ยนทันที
    ซึ่งคือสิ่งที่ต้องการ — ให้เอกสารเตือนว่าโค้ดไม่ตรงกับที่เขียนไว้
    """
    lane_w = 104
    lane_h = 34
    gutter = 158          # เว้นที่ซ้ายสำหรับข้อความกรณีใช้งาน ไม่ให้ลูกศรทับ
    width = gutter + lane_w * len(actors) + 24
    step_h = 30
    height = 70 + lane_h + 16 + step_h * len(statuses) + 58

    d = Drawing(width, height)
    text(d, 20, height - 22, 'แผนผังลำดับ: วงจรชีวิตออเดอร์', 12, INK, bold=True)

    top = height - 46
    xs = [gutter + i * lane_w + lane_w / 2 for i in range(len(actors))]

    for i, actor in enumerate(actors):
        d.add(Rect(xs[i] - lane_w / 2 + 8, top - 16, lane_w - 16, 18, rx=4, ry=4,
                   fillColor=BLUE_SOFT, strokeColor=BLUE, strokeWidth=0.9))
        text(d, xs[i] - lane_w / 2 + 8, top - 10.5, actor, 8, BLUE,
             bold=True, align='center', width=lane_w - 16)
        d.add(Line(xs[i], top - 17, xs[i], top - lane_h - step_h * len(statuses),
                   strokeColor=HexColor('#e2e6ec'), strokeWidth=1))

    y = top - lane_h - 10
    for idx, (label, actor) in enumerate(statuses):
        lane = xs[actors.index(actor)] if actor in actors else xs[0]
        d.add(Rect(20, y - 14, width - 40, 20, rx=3, ry=3,
                   fillColor=GREY_SOFT if idx % 2 == 0 else PAPER,
                   strokeColor=None))
        text(d, 26, y - 7.5, f'{idx + 1}.', 7.5, MUTED, bold=True)
        for li, line in enumerate(wrap(label, 7.8, gutter - 40)):
            text(d, 40, y - 7.5 - li * 9, line, 7.8, INK)
        arrow(d, lane, y + 6, lane, y - 13, color=INK_SOFT, width=1)
        y -= step_h

    note(d, 20, 14, width - 40,
         'กติกา: เดินทีละขั้นเท่านั้น ห้ามข้ามและห้ามถอยหลัง '
         '(บังคับที่ OrderStatusService.move) — ขั้น "ชำระเงินแล้ว" ขึ้นอัตโนมัติเมื่อ '
         'ยอดที่แจ้งครบตาม PaymentService เจ้าหน้าที่ตั้งเองไม่ได้ '
         '— ขั้นสุดท้ายให้ "ผู้รับสินค้า" เป็นคนยืนยันเพราะของถึงมือเมื่อผู้รับบอก '
         'ว่าได้รับแล้ว ไม่ใช่เมื่อผู้ส่งกดว่าส่งแล้ว',
         fill=BLUE_SOFT, stroke=BLUE, color=HexColor('#1b4f8f'), size=7.4)
    return d


# ---------------------------------------------------------------------------
# ไดอะแกรม 4: Use Case
# ---------------------------------------------------------------------------
def use_case_diagram(cases: dict[str, list[tuple[str, str]]],
                     title: str = 'Use Case Diagram') -> Drawing:
    """Use Case Diagram แบบตารางกลุ่มผู้ใช้

    ใช้รูปแบบตารางแทนวงรี/ผู้กระทำ เพราะระบบนี้มีกรณีใช้งานมาก
    (หลังบ้าน ~40 รายการ) วงรีจะบี้จนอ่านไม่ออก และวงรีด้วย reportlab
    ต้องคำนวณรัศมี — เป็นการเขียนโค้ดเพิ่มโดยได้ผลไม่คุ้ม

    Args:
        cases: {กลุ่มผู้ใช้: [(ชื่อกรณีใช้, คำอธิบายสั้น), ...]}
    """
    pad = 20
    header_h = 22
    row_h = 15.5
    name_w, desc_w = 150, 300
    width = pad * 2 + name_w + desc_w
    rows = sum(len(v) for v in cases.values())
    height = 58 + rows * row_h + sum(24 for _ in cases) + 20

    d = Drawing(width, height)
    text(d, pad, height - 22, title, 12, INK, bold=True)

    y = height - 46
    for group, items in cases.items():
        gh = 20
        d.add(Rect(pad, y - gh, name_w + desc_w, gh,
                   fillColor=PURPLE_SOFT, strokeColor=PURPLE, strokeWidth=0.8))
        text(d, pad + 8, y - gh + 6.5, f'ผู้กระทำ: {group}', 8.5, PURPLE, bold=True)
        y -= gh + 3

        for name, desc in items:
            d.add(Line(pad, y, pad + name_w + desc_w, y,
                       strokeColor=HexColor('#eef1f5'), strokeWidth=0.6))
            text(d, pad + 10, y - 10, name, 7.8, INK)
            text(d, pad + name_w + 4, y - 10, desc, 7.2, MUTED)
            y -= row_h
        y -= 6

    return d
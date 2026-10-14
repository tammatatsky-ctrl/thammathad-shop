"""สร้างเอกสารรายงานโครงงานเชิงวิชาการเป็น PDF (reportlab platypus)

รูปแบบเอกสารเป็นไปตามมาตรฐานการจัดทำเล่มรายงานโครงงานทางวิทยาการคอมพิวเตอร์
รายวิชา 4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์ (Special Topics in Computer Science)
สาขาวิชาวิทยาการคอมพิวเตอร์ คณะวิทยาศาสตร์และเทคโนโลยี มหาวิทยาลัยราชภัฏกำแพงเพชร

ผู้จัดทำ: นายธรรมธัช รูปไธสง (รหัสนักศึกษา 671320104)
อาจารย์ประจำวิชา / เสนอ: ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย

คุณลักษณะเด่น:
- ส่วนนำเชิงวิชาการครบถ้วน: ปกนอก, ปกใน, ใบรับรองโครงงาน, บทคัดย่อไทย-อังกฤษ,
  กิตติกรรมประกาศ, สารบัญเนื้อหา, สารบัญตาราง, และสารบัญภาพ
- ระบบเลขหน้า 2 ระบบ: ส่วนนำใช้ตัวอักษรไทย (ก, ข, ค...), ส่วนเนื้อหาเริ่มหน้า 1
- ระบบคำนวณเลขหน้าจริง (Two-Pass Page Numbering) สำหรับสารบัญทุกประเภท
- ไดอะแกรมฝังเป็น Vector Graphics คมชัดทุกระดับการซูมและพิมพ์
"""

from __future__ import annotations

import io
import os
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image,
                                KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from . import diagrams
from .diagrams import FONT_BOLD, FONT_REGULAR


PAGE_W, PAGE_H = A4
MARGIN_L = 35 * mm   # ขอบซ้าย 35 มม. (สำหรับเข้าเล่มรายงานวิชาการ)
MARGIN_R = 20 * mm   # ขอบขวา 20 มม.
MARGIN_T = 30 * mm   # ขอบบน 30 มม.
MARGIN_B = 22 * mm   # ขอบล่าง 22 มม.
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R
CONTENT_H = PAGE_H - MARGIN_T - MARGIN_B

THAI_NUMERALS = [
    'ก', 'ข', 'ค', 'ง', 'จ', 'ฉ', 'ช', 'ซ', 'ฌ', 'ญ',
    'ฎ', 'ฏ', 'ฐ', 'ฑ', 'ฒ', 'ณ', 'ด', 'ต', 'ถ', 'ท',
    'ธ', 'น', 'บ', 'ป', 'ผ', 'ฝ', 'พ', 'ฟ', 'ภ', 'ม',
    'ย', 'ร', 'ล', 'ว', 'ศ', 'ษ', 'ส', 'ห', 'ฬ', 'อ', 'ฮ'
]


def _styles() -> dict[str, ParagraphStyle]:
    """นิยามรูปแบบข้อความทั้งหมดของเอกสารตามหลักวิชาการ (ใช้สีดำล้วนตามข้อกำหนด)"""
    base = getSampleStyleSheet()['Normal']
    s: dict[str, ParagraphStyle] = {}

    s['body'] = ParagraphStyle(
        'body', parent=base, fontName=FONT_REGULAR, fontSize=10,
        leading=16.5, alignment=TA_LEFT, spaceAfter=6,
        wordWrap='CJK', textColor=diagrams.INK)
    s['body_indent'] = ParagraphStyle(
        'body_indent', parent=s['body'], firstLineIndent=22, spaceAfter=6)
    s['h1'] = ParagraphStyle(
        'h1', parent=base, fontName=FONT_BOLD, fontSize=16, leading=23,
        spaceBefore=14, spaceAfter=12, alignment=TA_CENTER, textColor=diagrams.INK,
        keepWithNext=True)
    s['h2'] = ParagraphStyle(
        'h2', parent=base, fontName=FONT_BOLD, fontSize=12.5, leading=18,
        spaceBefore=12, spaceAfter=6, textColor=diagrams.INK,
        keepWithNext=True)
    s['h3'] = ParagraphStyle(
        'h3', parent=base, fontName=FONT_BOLD, fontSize=10.5, leading=15,
        spaceBefore=8, spaceAfter=4, textColor=diagrams.INK,
        keepWithNext=True)
    s['bullet'] = ParagraphStyle(
        'bullet', parent=s['body'], leftIndent=18, bulletIndent=6,
        spaceAfter=3, alignment=TA_LEFT, wordWrap='CJK')
    s['td'] = ParagraphStyle(
        'td', parent=base, fontName=FONT_REGULAR, fontSize=8.5, leading=12.5,
        wordWrap='CJK', textColor=diagrams.INK)
    s['th'] = ParagraphStyle(
        'th', parent=base, fontName=FONT_BOLD, fontSize=8.5, leading=12.5,
        wordWrap='CJK', textColor=diagrams.INK)
    s['caption'] = ParagraphStyle(
        'caption', parent=base, fontName=FONT_BOLD, fontSize=8.5,
        leading=12.5, alignment=TA_CENTER, textColor=diagrams.INK,
        spaceBefore=4, spaceAfter=12)
    s['table_caption'] = ParagraphStyle(
        'table_caption', parent=base, fontName=FONT_BOLD, fontSize=9,
        leading=13, alignment=TA_LEFT, textColor=diagrams.INK,
        spaceBefore=8, spaceAfter=4, keepWithNext=True)
    s['ref_item'] = ParagraphStyle(
        'ref_item', parent=base, fontName=FONT_REGULAR, fontSize=8.8,
        leading=13.5, leftIndent=22, firstLineIndent=-22,
        spaceAfter=5, wordWrap='CJK', textColor=diagrams.INK)
    s['td_mono'] = ParagraphStyle(
        'td_mono', parent=s['td'], fontSize=8.0)
    s['note'] = ParagraphStyle(
        'note', parent=base, fontName=FONT_REGULAR, fontSize=8.8,
        leading=13.5, textColor=diagrams.INK)

    # สไตล์สำหรับหน้าปกและหน้าอนุมัติ (สีดำล้วน)
    s['cover_institution'] = ParagraphStyle(
        'cover_institution', parent=base, fontName=FONT_BOLD, fontSize=12,
        leading=18, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_report_type'] = ParagraphStyle(
        'cover_report_type', parent=base, fontName=FONT_BOLD, fontSize=13,
        leading=19, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_title'] = ParagraphStyle(
        'cover_title', parent=base, fontName=FONT_BOLD, fontSize=21,
        leading=29, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_title_en'] = ParagraphStyle(
        'cover_title_en', parent=base, fontName=FONT_BOLD, fontSize=12,
        leading=17, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_project'] = ParagraphStyle(
        'cover_project', parent=base, fontName=FONT_BOLD, fontSize=14,
        leading=20, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_sub'] = ParagraphStyle(
        'cover_sub', parent=base, fontName=FONT_REGULAR, fontSize=12,
        leading=18, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_meta'] = ParagraphStyle(
        'cover_meta', parent=base, fontName=FONT_REGULAR, fontSize=10.5,
        leading=18, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_meta_bold'] = ParagraphStyle(
        'cover_meta_bold', parent=base, fontName=FONT_BOLD, fontSize=10.5,
        leading=18, alignment=TA_CENTER, textColor=diagrams.INK)

    return s


_XML_ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}
_WS = re.compile(r'\s+')
_PARA_SPLIT = re.compile(r'\n[ \t]*\n')


def esc(text: str) -> str:
    """เตรียมข้อความให้พร้อมส่งเข้า Paragraph"""
    return _WS.sub(' ', ''.join(_XML_ESC.get(c, c) for c in str(text))).strip()


# ---------------------------------------------------------------------------
# วัตถุควบคุมเลขหน้าและสารบัญ (Page Anchors & Markers)
# ---------------------------------------------------------------------------
class PageAnchor(Flowable):
    """วัตถุบันทึกหมายเลขหน้าที่ปรากฏจริง เพื่อส่งให้สารบัญใน pass ถัดไป"""

    def __init__(self, key: str, registry: dict[str, int]):
        super().__init__()
        self.key = key
        self.registry = registry
        self.width = 0
        self.height = 0

    def wrap(self, avail_width, avail_height):
        return 0, 0

    def draw(self):
        self.registry[self.key] = self.canv.getPageNumber()


class _ChapterMarker(Flowable):
    """ส่งต่อชื่อบทปัจจุบันให้ Canvas สำหรับพิมพ์บนหัวกระดาษ"""

    def __init__(self, title: str, sink: list[str]):
        super().__init__()
        self.title = title
        self.sink = sink
        self.width = 0
        self.height = 0

    def wrap(self, avail_width, avail_height):
        return 0, 0

    def draw(self):
        self.sink[:] = [self.title]


# ---------------------------------------------------------------------------
# ส่วนประกอบหน้าเอกสาร (Cover, Approval, TOC, Tables, Figures)
# ---------------------------------------------------------------------------
def _cover(meta: dict[str, Any], is_inner: bool = False) -> list:
    """หน้าปกนอกและหน้าปกในตามรูปแบบวิชาการ"""
    s = _styles()
    title_th = meta.get('title', 'ระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์และไอที')
    title_en = meta.get('title_en', 'E-Commerce System for Computer Hardware and IT Accessories')
    student = meta.get('student', {})
    name = student.get('ชื่อ-นามสกุล', 'นายธรรมธัช รูปไธสง')
    std_id = student.get('รหัสนักศึกษา', '671320104')
    dept = student.get('สาขา', 'วิทยาการคอมพิวเตอร์')
    faculty = student.get('คณะ', 'คณะวิทยาศาสตร์และเทคโนโลยี')
    advisor = meta.get('advisor', 'ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย')
    course = meta.get('course', '4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์')
    univ = meta.get('university', 'มหาวิทยาลัยราชภัฏกำแพงเพชร')
    year = meta.get('year', '2569')

    story = [
        Spacer(1, 15 * mm),
        Paragraph('รายงานโครงงานทางวิทยาการคอมพิวเตอร์', s['cover_report_type']),
        Spacer(1, 4 * mm),
        Paragraph('ภาคการศึกษาที่ 1 ปีการศึกษา 2569', s['cover_meta']),
        Spacer(1, 14 * mm),
        Paragraph(esc(title_th), s['cover_title']),
        Spacer(1, 3 * mm),
        Paragraph('(THAMMATHAD SHOP)', s['cover_project']),
        Spacer(1, 3 * mm),
        Paragraph(esc(title_en), s['cover_title_en']),
        Spacer(1, 22 * mm),
        Paragraph('<b>ผู้จัดทำ</b>', s['cover_meta_bold']),
        Spacer(1, 2 * mm),
        Paragraph(esc(name) if name else '________________________________', s['cover_meta']),
        Paragraph(f'รหัสนักศึกษา {esc(std_id)}' if std_id else 'รหัสนักศึกษา ____________________', s['cover_meta']),
        Spacer(1, 10 * mm),
        Paragraph('<b>เสนอ</b>', s['cover_meta_bold']),
        Spacer(1, 2 * mm),
        Paragraph(esc(advisor) if advisor else '________________________________', s['cover_meta']),
        Spacer(1, 14 * mm),
        Paragraph(f'รายงานนี้เป็นส่วนหนึ่งของรายวิชา {esc(course)}', s['cover_meta']),
        Paragraph(f'สาขาวิชา{esc(dept)} {esc(faculty)}', s['cover_meta']),
        Paragraph(esc(univ), s['cover_meta_bold']),
        Paragraph(f'ปีการศึกษา {esc(year)}', s['cover_meta']),
    ]
    return story


def _approval(meta: dict[str, Any]) -> list:
    """หน้าใบรับรองรายงานโครงงานเชิงวิชาการ"""
    s = _styles()
    title_th = meta.get('title', 'ระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์และไอที')
    student = meta.get('student', {})
    name = student.get('ชื่อ-นามสกุล', 'นายธรรมธัช รูปไธสง')
    std_id = student.get('รหัสนักศึกษา', '671320104')
    dept = student.get('สาขา', 'วิทยาการคอมพิวเตอร์')
    faculty = student.get('คณะ', 'คณะวิทยาศาสตร์และเทคโนโลยี')
    advisor = meta.get('advisor', 'ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย')
    course = meta.get('course', '4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์')
    univ = meta.get('university', 'มหาวิทยาลัยราชภัฏกำแพงเพชร')
    year = meta.get('year', '2569')

    info_rows = [
        [Paragraph('<b>ชื่อโครงงาน</b>', s['td']), Paragraph(esc(title_th) + ' (THAMMATHAD SHOP)', s['td'])],
        [Paragraph('<b>ผู้จัดทำ</b>', s['td']), Paragraph(f'{esc(name)}  รหัสนักศึกษา {esc(std_id)}', s['td'])],
        [Paragraph('<b>รายวิชา</b>', s['td']), Paragraph(esc(course), s['td'])],
        [Paragraph('<b>สาขาวิชา</b>', s['td']), Paragraph(f'{esc(dept)}  {esc(faculty)}', s['td'])],
        [Paragraph('<b>สถาบัน</b>', s['td']), Paragraph(esc(univ), s['td'])],
        [Paragraph('<b>ปีการศึกษา</b>', s['td']), Paragraph(esc(year), s['td'])],
    ]
    table = Table(info_rows, colWidths=[32 * mm, CONTENT_W - 32 * mm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    story = [
        Spacer(1, 10 * mm),
        Paragraph('ใบรับรองรายงานโครงงาน', s['h1']),
        Spacer(1, 2 * mm),
        Paragraph(f'สาขาวิชา{esc(dept)} {esc(faculty)} {esc(univ)}', s['caption']),
        Spacer(1, 10 * mm),
        table,
        Spacer(1, 10 * mm),
        Paragraph(
            'ได้รับการพิจารณาอนุมัติให้เป็นส่วนหนึ่งของการศึกษาตามหลักสูตรวิทยาศาสตรบัณฑิต '
            f'สาขาวิชา{esc(dept)} ในรายวิชา {esc(course)}', s['body_indent']),
        Spacer(1, 26 * mm),
        Paragraph('ลงชื่อ ................................................................ อาจารย์ประจำวิชา', s['cover_meta']),
        Spacer(1, 3 * mm),
        Paragraph(f'({esc(advisor)})', s['cover_meta_bold']),
        Spacer(1, 3 * mm),
        Paragraph('วันที่ ........ เดือน ........................ พ.ศ. ' + esc(year), s['cover_meta']),
    ]
    return story


def _acknowledgements(meta: dict[str, Any], text: str) -> list:
    """หน้ากิตติกรรมประกาศ"""
    s = _styles()
    student = meta.get('student', {})
    name = student.get('ชื่อ-นามสกุล', 'นายธรรมธัช รูปไธสง')

    story = [
        Paragraph('กิตติกรรมประกาศ', s['h1']),
        Spacer(1, 8 * mm),
    ]
    for chunk in _PARA_SPLIT.split(text):
        chunk = chunk.strip()
        if chunk:
            story.append(Paragraph(esc(chunk), s['body_indent']))
            story.append(Spacer(1, 4))
    story += [
        Spacer(1, 16 * mm),
        Paragraph(esc(name), s['cover_meta_bold']),
        Paragraph('ผู้จัดทำโครงงาน', s['cover_meta']),
    ]
    return story


def _toc(entries: list[tuple[str, str, str | int]]) -> list:
    """สารบัญเนื้อหา (Table of Contents)"""
    s = _styles()
    rows = [
        [Paragraph('<b>ลำดับ</b>', s['th']),
         Paragraph('<b>ชื่อบท / หัวข้อเรื่อง</b>', s['th']),
         Paragraph('<b>หน้า</b>', s['th'])],
    ]
    for num, title, page in entries:
        is_chapter = num.startswith('บทที่') or num.startswith('ภาค') or num in ('บทคัดย่อ', 'เอกสารอ้างอิง')
        cell_style = s['td']
        num_text = f'<b>{esc(num)}</b>' if is_chapter else esc(num)
        title_text = f'<b>{esc(title)}</b>' if is_chapter else f'&nbsp;&nbsp;&nbsp;&nbsp;{esc(title)}'
        rows.append([
            Paragraph(num_text, cell_style),
            Paragraph(title_text, cell_style),
            Paragraph(str(page), cell_style),
        ])

    table = Table(rows, colWidths=[20 * mm, CONTENT_W - 36 * mm, 16 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, colors.HexColor('#e0e0e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    return [Paragraph('สารบัญเนื้อหา', s['h1']), Spacer(1, 4 * mm), table]


def _lot(table_entries: list[tuple[str, str, str | int]]) -> list:
    """สารบัญตาราง (List of Tables)"""
    s = _styles()
    rows = [
        [Paragraph('<b>ตารางที่</b>', s['th']),
         Paragraph('<b>ชื่อตาราง</b>', s['th']),
         Paragraph('<b>หน้า</b>', s['th'])],
    ]
    for num, title, page in table_entries:
        rows.append([
            Paragraph(esc(num), s['td']),
            Paragraph(esc(title), s['td']),
            Paragraph(str(page), s['td']),
        ])

    table = Table(rows, colWidths=[24 * mm, CONTENT_W - 40 * mm, 16 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, colors.HexColor('#e0e0e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    return [Paragraph('สารบัญตาราง', s['h1']), Spacer(1, 4 * mm), table]


def _lof(figure_entries: list[tuple[str, str, str | int]]) -> list:
    """สารบัญภาพ (List of Figures)"""
    s = _styles()
    rows = [
        [Paragraph('<b>ภาพที่</b>', s['th']),
         Paragraph('<b>ชื่อภาพและคำบรรยาย</b>', s['th']),
         Paragraph('<b>หน้า</b>', s['th'])],
    ]
    for num, title, page in figure_entries:
        rows.append([
            Paragraph(esc(num), s['td']),
            Paragraph(esc(title), s['td']),
            Paragraph(str(page), s['td']),
        ])

    table = Table(rows, colWidths=[24 * mm, CONTENT_W - 40 * mm, 16 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, colors.HexColor('#e0e0e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    return [Paragraph('สารบัญภาพ', s['h1']), Spacer(1, 4 * mm), table]


def _figure(drawing, caption: str, styles: dict, anchor: Flowable | None = None) -> list:
    """ฝังไดอะแกรมเวกเตอร์ + คำบรรยายใต้ภาพ (ผูกติดกันด้วย KeepTogether เพื่อไม่ให้แยกหน้า)"""
    s = styles
    scale = min(1.0, CONTENT_W / drawing.width)
    img = Image(drawing, width=drawing.width * scale,
                height=drawing.height * scale)
    elements = []
    if anchor:
        elements.append(anchor)
    elements.extend([
        Spacer(1, 4),
        img,
        Spacer(1, 3),
        Paragraph(esc(caption), s['caption']),
        Spacer(1, 6),
    ])
    return [KeepTogether(elements)]


def _data_table(spec: dict, styles: dict, widths=None, anchor: Flowable | None = None) -> list:
    """ตารางข้อมูลพร้อมคำอธิบายหัวตาราง (Table Caption ด้านบนตามหลักวิชาการ)"""
    s = styles
    flowables = []
    if anchor:
        flowables.append(anchor)
    if 'title' in spec and spec['title']:
        flowables.append(Paragraph(esc(spec['title']), s['table_caption']))

    head = [Paragraph(esc(h), s['th']) for h in spec['head']]
    body = [[Paragraph(esc(c), s['td']) for c in row] for row in spec['rows']]
    table = Table([head] + body, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d0d0d0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#fafafa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5.5),
    ]))
    flowables.append(table)
    if 'title' in spec and spec['title']:
        return [KeepTogether(flowables)]
    return flowables


def _block_renderer(blocks, styles: dict) -> list:
    """แปลงบล็อกเนื้อหาเป็น flowable ของ platypus"""
    s = styles
    out: list = []
    for block in blocks:
        kind = block[0]
        if kind == 'h2':
            out.append(Paragraph(esc(block[1]), s['h2']))
        elif kind == 'h3':
            out.append(Paragraph(esc(block[1]), s['h3']))
        elif kind == 'p':
            for chunk in _PARA_SPLIT.split(block[1]):
                chunk = chunk.strip()
                if chunk:
                    style = s['body'] if chunk.startswith('<b>') else s['body_indent']
                    out.append(Paragraph(esc(chunk), style))
                    out.append(Spacer(1, 3))
        elif kind == 'note':
            out.append(Paragraph(esc(block[1]), s['note']))
            out.append(Spacer(1, 5))
        elif kind == 'bullets':
            for item in block[1]:
                text, detail = (item if isinstance(item, tuple)
                                else (item, ''))
                out.append(Paragraph(
                    f'<bullet>&bull;</bullet>{esc(text)}{esc(detail)}',
                    s['bullet']))
            out.append(Spacer(1, 5))
        elif kind == 'table':
            out.extend(_data_table(block[1], s))
            out.append(Spacer(1, 10))
        elif kind == 'focus':
            out.append(Paragraph('ตารางที่ 4.1 สาระสำคัญของการทดสอบระบบ (Test Focus)', s['table_caption']))
            rows = [[Paragraph(esc(a), s['td']), Paragraph(esc(b), s['td'])]
                    for a, b in block[1]]
            table = Table(rows, colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.65])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d0d0d0')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                ('TOPPADDING', (0, 0), (-1, -1), 4.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            out.append(table)
            out.append(Spacer(1, 10))
        elif kind == 'ref_item':
            out.append(Paragraph(esc(block[1]), s['ref_item']))
    return out


# ---------------------------------------------------------------------------
# ตัวสร้างเอกสาร PDF (Two-Pass Builder)
# ---------------------------------------------------------------------------
def _create_doc_templates(target: str, meta: dict, current_chapter: list[str],
                          main_start_box: list[int]) -> BaseDocTemplate:
    """สร้าง BaseDocTemplate พร้อม PageTemplates สำหรับส่วนนำและส่วนเนื้อหา"""
    doc = BaseDocTemplate(
        target, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=meta.get('title', ''), author=meta.get('student', {}).get('ชื่อ-นามสกุล', ''))

    frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W, CONTENT_H, id='main')

    def on_cover(canvas, _doc):
        # หน้าปกนอก, ปกใน, ใบรับรอง: ไม่มีหัวกระดาษและเลขหน้า
        pass

    def on_prelim(canvas, _doc):
        # ส่วนนำ (บทคัดย่อ, กิตติกรรมประกาศ, สารบัญ): เลขหน้าตัวอักษรไทย ก, ข, ค... มุมบนขวา
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 9)
        canvas.setFillColor(diagrams.INK)
        p = canvas.getPageNumber() - 4  # หัก 3 หน้าแรกออก (ปกนอก ปกใน ใบรับรอง) -> หน้าที่ 4 คือ ก
        label = THAI_NUMERALS[p] if 0 <= p < len(THAI_NUMERALS) else str(p + 1)
        canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 12, label)
        canvas.restoreState()

    def on_chapter_first(canvas, _doc):
        # หน้าแรกของแต่ละบท: ไม่พิมพ์เลขหน้าและไม่มีหัวกระดาษตามมาตรฐานวิชาการ
        pass

    def on_chapter_body(canvas, _doc):
        # หน้าเนื้อหาทั่วไป: มีเส้นหัวกระดาษสีดำบาง และเลขหน้าอารบิกมุมบนขวา
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 8.5)
        canvas.setFillColor(diagrams.INK)
        header_text = 'รายงานโครงงาน: THAMMATHAD SHOP'
        if current_chapter and current_chapter[0]:
            header_text += f'  |  {current_chapter[0][:55]}'
        canvas.drawString(MARGIN_L, PAGE_H - MARGIN_T + 10, header_text)

        arabic_page = canvas.getPageNumber() - main_start_box[0] + 1
        canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 10, str(arabic_page))

        canvas.setStrokeColor(diagrams.LINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_L, PAGE_H - MARGIN_T + 5, PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 5)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[frame], onPage=on_cover),
        PageTemplate(id='prelim', frames=[frame], onPage=on_prelim),
        PageTemplate(id='chapter_first', frames=[frame], onPage=on_chapter_first),
        PageTemplate(id='chapter_body', frames=[frame], onPage=on_chapter_body),
    ])
    return doc


def _build_story(meta: dict, chapters: list[dict], diagrams_pack: dict,
                 appendix_blocks: list[dict], current_chapter: list[str],
                 page_registry: dict[str, int], main_start_box: list[int],
                 is_pass2: bool = False) -> list:
    """สร้าง Story ทั้งเล่มรายงาน พร้อมจัดลำดับ Template สอดคล้องตามหลักวิชาการ"""
    styles = _styles()
    story: list = []

    # 1. หน้าปกนอก (Outer Cover) -> Template: cover
    story += _cover(meta, is_inner=False)
    story.append(NextPageTemplate('cover'))
    story.append(PageBreak())

    # 2. หน้าปกใน (Inner Cover) -> Template: cover
    story += _cover(meta, is_inner=True)
    story.append(NextPageTemplate('cover'))
    story.append(PageBreak())

    # 3. ใบรับรองรายงานโครงงาน (Approval Page) -> Template: cover
    story += _approval(meta)
    story.append(NextPageTemplate('prelim'))
    story.append(PageBreak())

    # 4. ส่วนนำ -> Template: prelim (เลขหน้าภาษาไทย ก, ข, ค...)
    from .content import ABSTRACT_THAI, ABSTRACT_EN, KEYWORDS_TH, KEYWORDS_EN, ACKNOWLEDGEMENTS

    # 4.1 บทคัดย่อภาษาไทย
    story.append(PageAnchor('abstract_th', page_registry))
    story.append(Paragraph('บทคัดย่อภาษาไทย', styles['h1']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(esc(ABSTRACT_THAI), styles['body_indent']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f'<b>คำสำคัญ:</b> {esc(KEYWORDS_TH)}', styles['body']))
    story.append(PageBreak())

    # 4.2 บทคัดย่อภาษาอังกฤษ (Abstract)
    story.append(PageAnchor('abstract_en', page_registry))
    story.append(Paragraph('Abstract', styles['h1']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(esc(ABSTRACT_EN), styles['body_indent']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f'<b>Keywords:</b> {esc(KEYWORDS_EN)}', styles['body']))
    story.append(PageBreak())

    # 4.3 กิตติกรรมประกาศ
    story.append(PageAnchor('acknowledgements', page_registry))
    story += _acknowledgements(meta, ACKNOWLEDGEMENTS)
    story.append(PageBreak())

    # ฟังก์ชันแปลงเลขหน้าตามจริง
    def p_num(key: str, default: int = 1) -> str:
        if not is_pass2 or key not in page_registry:
            return str(default)
        raw_p = page_registry[key]
        start_p = main_start_box[0] or 1
        arabic = max(1, raw_p - start_p + 1)
        return str(arabic)

    def p_prelim(key: str, default: str = 'ก') -> str:
        if not is_pass2 or key not in page_registry:
            return default
        raw_p = page_registry[key]
        idx = raw_p - 4
        return THAI_NUMERALS[idx] if 0 <= idx < len(THAI_NUMERALS) else str(idx + 1)

    # 4.4 สารบัญเนื้อหา (Table of Contents)
    story.append(PageAnchor('toc', page_registry))
    toc_entries = [
        ('บทคัดย่อ', 'บทคัดย่อภาษาไทย', p_prelim('abstract_th', 'ก')),
        ('Abstract', 'Abstract (บทคัดย่อภาษาอังกฤษ)', p_prelim('abstract_en', 'ข')),
        ('กิตติกรรม', 'กิตติกรรมประกาศ', p_prelim('acknowledgements', 'ค')),
        ('สารบัญ', 'สารบัญเนื้อหา', p_prelim('toc', 'ง')),
        ('สารบัญตาราง', 'สารบัญตาราง', p_prelim('lot', 'ฉ')),
        ('สารบัญภาพ', 'สารบัญภาพ', p_prelim('lof', 'ช')),
        ('บทที่ 1', 'บทนำ', p_num('ch_intro', 1)),
        ('1.1', 'ความเป็นมาและความสำคัญของปัญหา', p_num('sec_1_1', 1)),
        ('1.2', 'วัตถุประสงค์ของโครงการ', p_num('sec_1_2', 1)),
        ('1.3', 'ขอบเขตของโครงการ', p_num('sec_1_3', 2)),
        ('1.4', 'ประเภทผู้ใช้งานและระดับสิทธิ์ในระบบ', p_num('sec_1_4', 3)),
        ('1.5', 'แผนการดำเนินงานและระเบียบวิธีพัฒนา', p_num('sec_1_5', 4)),
        ('1.6', 'นิยามศัพท์เฉพาะ', p_num('sec_1_6', 4)),
        ('บทที่ 2', 'ทฤษฎีและเทคโนโลยีที่เกี่ยวข้อง', p_num('ch_tools', 5)),
        ('2.1', 'สถาปัตยกรรมซอฟต์แวร์และการออกแบบเชิงระบบ', p_num('sec_2_1', 5)),
        ('2.2', 'การเขียนโปรแกรมเชิงวัตถุและแบบแผนการออกแบบ', p_num('sec_2_2', 5)),
        ('2.3', 'เทคโนโลยีและเฟรมเวิร์กที่ใช้ในการพัฒนา', p_num('sec_2_3', 6)),
        ('2.4', 'ทฤษฎีความปลอดภัยสำหรับเว็บแอปพลิเคชัน', p_num('sec_2_4', 7)),
        ('2.5', 'เทคโนโลยีการชำระเงินดิจิทัลและมาตรฐาน QR Code', p_num('sec_2_5', 8)),
        ('2.6', 'การวิเคราะห์เปรียบเทียบกับระบบที่เกี่ยวข้อง', p_num('sec_2_6', 8)),
        ('บทที่ 3', 'การวิเคราะห์และการออกแบบระบบ', p_num('ch_analysis', 9)),
        ('3.1', 'การวิเคราะห์ความต้องการของระบบ', p_num('sec_3_1', 9)),
        ('3.2', 'การวิเคราะห์กรณีการใช้งาน (Use Case Analysis)', p_num('sec_3_2', 9)),
        ('3.3', 'การออกแบบสถาปัตยกรรมระบบ (System Architecture)', p_num('sec_3_3', 10)),
        ('3.4', 'การออกแบบแบบจำลองข้อมูล (Data Modeling & ERD)', p_num('sec_3_4', 11)),
        ('3.5', 'การออกแบบเครื่องจักรสถานะคำสั่งซื้อ (Order State Machine)', p_num('sec_3_5', 12)),
        ('3.6', 'การออกแบบส่วนต่อประสานผู้ใช้ (User Interface Design)', p_num('sec_3_6', 13)),
        ('บทที่ 4', 'การพัฒนาและผลการทดสอบระบบ', p_num('ch_testing', 14)),
        ('4.1', 'ระเบียบวิธีและกลยุทธ์การทดสอบ', p_num('sec_4_1', 14)),
        ('4.2', 'สาระสำคัญของการทดสอบระบบ', p_num('sec_4_2', 14)),
        ('4.3', 'สรุปผลการรันชุดทดสอบอัตโนมัติ (383 Test Cases)', p_num('sec_4_3', 15)),
        ('บทที่ 5', 'บทสรุป อภิปรายผล และข้อเสนอแนะ', p_num('ch_conclusion', 16)),
        ('5.1', 'สรุปผลการดำเนินงาน', p_num('sec_5_1', 16)),
        ('5.2', 'อภิปรายผลการพัฒนาระบบ', p_num('sec_5_2', 16)),
        ('5.3', 'ปัญหา อุปสรรค และแนวทางการแก้ไข', p_num('sec_5_3', 17)),
        ('5.4', 'ข้อจำกัดของระบบ', p_num('sec_5_4', 17)),
        ('5.5', 'ข้อเสนอแนะและทิศทางการพัฒนาต่อยอด', p_num('sec_5_5', 18)),
        ('เอกสารอ้างอิง', 'รายการเอกสารอ้างอิงและบรรณานุกรม', p_num('ch_references', 19)),
        ('ภาคผนวก ก', 'พจนานุกรมข้อมูลและโครงสร้างระบบ', p_num('ch_appendix', 20)),
        ('ภาคผนวก ข', 'ประวัติผู้จัดทำโครงงาน', p_num('ch_bio', 24)),
    ]
    story += _toc(toc_entries)
    story.append(PageBreak())

    # 4.4 สารบัญตาราง (List of Tables)
    story.append(PageAnchor('lot', page_registry))
    lot_entries = [
        ('ตารางที่ 1.1', 'ขอบเขตของโครงการ', p_num('tab_1_1', 2)),
        ('ตารางที่ 1.2', 'ประเภทผู้ใช้งานและระดับสิทธิ์ในระบบ', p_num('tab_1_2', 3)),
        ('ตารางที่ 2.1', 'เทคโนโลยีและเครื่องมือที่ใช้ในการพัฒนา', p_num('tab_2_1', 6)),
        ('ตารางที่ 2.2', 'การวิเคราะห์เปรียบเทียบกับระบบที่เกี่ยวข้อง', p_num('tab_2_2', 8)),
        ('ตารางที่ 4.1', 'สาระสำคัญของการทดสอบระบบ (Test Focus)', p_num('tab_4_1', 14)),
        ('ตารางที่ 4.2', 'สรุปผลการประเมินชุดการทดสอบอัตโนมัติ', p_num('tab_4_2', 15)),
        ('ตารางที่ 5.1', 'ปัญหา อุปสรรค และแนวทางการแก้ไข', p_num('tab_5_1', 17)),
        ('ตารางที่ 5.2', 'ข้อจำกัดของระบบในปัจจุบัน', p_num('tab_5_2', 17)),
    ]
    story += _lot(lot_entries)
    story.append(PageBreak())

    # 4.5 สารบัญภาพ (List of Figures)
    story.append(PageAnchor('lof', page_registry))
    lof_entries = [
        ('ภาพที่ 3.1', 'แผนภาพกรณีการใช้งานของระบบ (Use Case Diagram)', p_num('fig_3_1', 10)),
        ('ภาพที่ 3.2', 'แผนภาพสถาปัตยกรรมระบบแบบ 4 ชั้น (4-Layer System Architecture)', p_num('fig_3_2', 11)),
        ('ภาพที่ 3.3', 'แผนภาพความสัมพันธ์ข้อมูล (Entity-Relationship Diagram - ERD)', p_num('fig_3_3', 12)),
        ('ภาพที่ 3.4', 'แผนผังวงจรชีวิตสถานะคำสั่งซื้อ (Order Lifecycle State Transition)', p_num('fig_3_4', 13)),
    ]
    story += _lof(lof_entries)
    # เตรียมเปลี่ยนเป็น 'chapter_first' สำหรับหน้าแรกของบทที่ 1
    story.append(NextPageTemplate('chapter_first'))
    story.append(PageBreak())

    # 5. ส่วนเนื้อหาหลัก 5 บท + เอกสารอ้างอิง: เริ่มนับหน้า 1
    body_chapters = [c for c in chapters if c['id'] not in ('abstract',)]
    for idx, chapter in enumerate(body_chapters):
        ch_id = chapter['id']
        story.append(PageAnchor(f'ch_{ch_id}', page_registry))
        story.append(_ChapterMarker(chapter['title'], current_chapter))
        story.append(Paragraph(esc(chapter['title']), styles['h1']))
        story.append(Spacer(1, 4 * mm))
        # หน้าถัดไปของบทเดียวกันให้ใช้ chapter_body (มีเส้นหัวกระดาษ)
        story.append(NextPageTemplate('chapter_body'))

        # แทรก PageAnchors และ Figures ในตำแหน่งที่ถูกต้องของบท
        blocks = chapter['blocks']
        for block in blocks:
            kind = block[0]
            if kind == 'h2':
                title_text = block[1]
                if '1.1' in title_text: story.append(PageAnchor('sec_1_1', page_registry))
                elif '1.2' in title_text: story.append(PageAnchor('sec_1_2', page_registry))
                elif '1.3' in title_text: story.append(PageAnchor('sec_1_3', page_registry))
                elif '1.4' in title_text: story.append(PageAnchor('sec_1_4', page_registry))
                elif '1.5' in title_text: story.append(PageAnchor('sec_1_5', page_registry))
                elif '1.6' in title_text: story.append(PageAnchor('sec_1_6', page_registry))
                elif '2.1' in title_text: story.append(PageAnchor('sec_2_1', page_registry))
                elif '2.2' in title_text: story.append(PageAnchor('sec_2_2', page_registry))
                elif '2.3' in title_text: story.append(PageAnchor('sec_2_3', page_registry))
                elif '2.4' in title_text: story.append(PageAnchor('sec_2_4', page_registry))
                elif '2.5' in title_text: story.append(PageAnchor('sec_2_5', page_registry))
                elif '2.6' in title_text: story.append(PageAnchor('sec_2_6', page_registry))
                elif '3.1' in title_text: story.append(PageAnchor('sec_3_1', page_registry))
                elif '3.2' in title_text: story.append(PageAnchor('sec_3_2', page_registry))
                elif '3.3' in title_text: story.append(PageAnchor('sec_3_3', page_registry))
                elif '3.4' in title_text: story.append(PageAnchor('sec_3_4', page_registry))
                elif '3.5' in title_text: story.append(PageAnchor('sec_3_5', page_registry))
                elif '3.6' in title_text: story.append(PageAnchor('sec_3_6', page_registry))
                elif '4.1' in title_text: story.append(PageAnchor('sec_4_1', page_registry))
                elif '4.2' in title_text: story.append(PageAnchor('sec_4_2', page_registry))
                elif '4.3' in title_text: story.append(PageAnchor('sec_4_3', page_registry))
                elif '5.1' in title_text: story.append(PageAnchor('sec_5_1', page_registry))
                elif '5.2' in title_text: story.append(PageAnchor('sec_5_2', page_registry))
                elif '5.3' in title_text: story.append(PageAnchor('sec_5_3', page_registry))
                elif '5.4' in title_text: story.append(PageAnchor('sec_5_4', page_registry))
                elif '5.5' in title_text: story.append(PageAnchor('sec_5_5', page_registry))

            if kind == 'table':
                t_title = block[1].get('title', '')
                t_str = str(block[1])
                anchor_key = None
                if '1.1' in t_title or 'ด้านขอบเขต' in t_str:
                    anchor_key = 'tab_1_1'
                elif '1.2' in t_title or 'บทบาทผู้ใช้งาน' in t_str:
                    anchor_key = 'tab_1_2'
                elif '2.1' in t_title or ('Django' in t_str and len(block[1].get('rows', [])) == 8):
                    anchor_key = 'tab_2_1'
                elif '2.2' in t_title or 'จุดรับชำระเงิน' in t_str:
                    anchor_key = 'tab_2_2'
                elif '4.2' in t_title or '383' in t_str:
                    anchor_key = 'tab_4_2'
                elif '5.1' in t_title or 'Django Form' in t_str:
                    anchor_key = 'tab_5_1'
                elif '5.2' in t_title or 'Core Banking' in t_str:
                    anchor_key = 'tab_5_2'

                anchor_obj = PageAnchor(anchor_key, page_registry) if anchor_key else None
                story += _data_table(block[1], styles, anchor=anchor_obj)
                story.append(Spacer(1, 10))
                continue

            if kind == 'focus':
                anchor_obj = PageAnchor('tab_4_1', page_registry)
                focus_flowables = [
                    anchor_obj,
                    Paragraph('ตารางที่ 4.1 สาระสำคัญของการทดสอบระบบ (Test Focus)', styles['table_caption'])
                ]
                rows = [[Paragraph(esc(a), styles['td']), Paragraph(esc(b), styles['td'])]
                        for a, b in block[1]]
                table = Table(rows, colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.65])
                table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d0d0d0')),
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4.5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                focus_flowables.append(table)
                story.append(KeepTogether(focus_flowables))
                story.append(Spacer(1, 10))
                continue

            story += _block_renderer([block], styles)

            # ฝังไดอะแกรมเวกเตอร์ในบทที่ 3 ให้สอดคล้องกับเนื้อหา
            if ch_id == 'analysis' and kind == 'h2':
                if '3.2' in block[1] and 'usecase' in diagrams_pack:
                    d, cap = diagrams_pack['usecase']
                    anchor_obj = PageAnchor('fig_3_1', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif '3.3' in block[1] and 'layered' in diagrams_pack:
                    d, cap = diagrams_pack['layered']
                    anchor_obj = PageAnchor('fig_3_2', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif '3.4' in block[1] and 'er' in diagrams_pack:
                    d, cap = diagrams_pack['er']
                    anchor_obj = PageAnchor('fig_3_3', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif '3.5' in block[1] and 'lifecycle' in diagrams_pack:
                    d, cap = diagrams_pack['lifecycle']
                    anchor_obj = PageAnchor('fig_3_4', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)

        # ก่อนจบบท เตรียมเปลี่ยนหน้าใหม่เป็น 'chapter_first'
        story.append(NextPageTemplate('chapter_first'))
        story.append(PageBreak())

    # 6. ภาคผนวก
    if appendix_blocks:
        story.append(PageAnchor('ch_appendix', page_registry))
        story.append(_ChapterMarker('ภาคผนวก ก ฐานข้อมูลและไดอะแกรม', current_chapter))
        story.append(Paragraph('ภาคผนวก ก — พจนานุกรมข้อมูลและโครงสร้างระบบ', styles['h1']))
        story.append(Spacer(1, 4 * mm))
        story.append(NextPageTemplate('chapter_body'))
        for block in appendix_blocks:
            kind = block[0]
            if kind == 'h2' and 'ภาคผนวก ข' in block[1]:
                story.append(NextPageTemplate('chapter_first'))
                story.append(PageBreak())
                story.append(PageAnchor('ch_bio', page_registry))
                story.append(_ChapterMarker('ภาคผนวก ข ประวัติผู้จัดทำ', current_chapter))
                story.append(Paragraph(esc(block[1]), styles['h1']))
                story.append(Spacer(1, 4 * mm))
                story.append(NextPageTemplate('chapter_body'))
                continue
            story += _block_renderer([block], styles)

    return story


def build_pdf(target: str, meta: dict, chapters: list[dict], diagrams_pack: dict,
              appendix_blocks: list[dict]) -> str:
    """ประกอบเอกสารรายงาน PDF เชิงวิชาการทั้งเล่ม (Two-Pass Page Numbering)"""
    diagrams.register_thai_fonts()

    # Pass 1: บันทึกเลขหน้าจริงของแต่ละส่วนลงใน page_registry
    page_registry: dict[str, int] = {}
    current_chapter: list[str] = ['']
    main_start_box: list[int] = [0]

    dummy_target = io.BytesIO()
    doc1 = _create_doc_templates(dummy_target, meta, current_chapter, main_start_box)
    story1 = _build_story(meta, chapters, diagrams_pack, appendix_blocks,
                          current_chapter, page_registry, main_start_box, is_pass2=False)
    doc1.build(story1)

    # กำหนดหมายเลขหน้าที่บทที่ 1 เริ่มต้น (เพื่อใช้คำนวณเลขอารบิก)
    main_start_page = page_registry.get('ch_intro', 11)
    main_start_box[0] = main_start_page

    # Pass 2: สร้างเอกสารฉบับสมบูรณ์พร้อมเลขหน้าจริงในสารบัญ
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    current_chapter = ['']
    doc2 = _create_doc_templates(target, meta, current_chapter, main_start_box)
    story2 = _build_story(meta, chapters, diagrams_pack, appendix_blocks,
                          current_chapter, page_registry, main_start_box, is_pass2=True)
    doc2.build(story2)

    return target
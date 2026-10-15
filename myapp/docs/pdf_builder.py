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
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, Image,
                                KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from . import diagrams
from .content import TOTAL_TESTS
from .diagrams import FONT_BOLD, FONT_REGULAR, adjust_thai, unshape_thai


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

_wrapped_patched = False


def _install_thai_word_wrap() -> None:
    """ติดตั้งระบบตัดคำภาษาไทยให้กับ reportlab Paragraph
    
    แก้ปัญหา 'คำขาดกัน' และ 'ตัวสระซ้อนกัน':
    - แปลงโทเค็นคำด้วย pythainlp เพื่อไม่ให้ตัดกลางคำภาษาไทย
    - ปรับตำแหน่งสระและวรรณยุกต์ (PUA) อัตโนมัติในแต่ละบรรทัด
    """
    global _wrapped_patched
    if _wrapped_patched:
        return

    import pythainlp
    from reportlab.pdfbase.pdfmetrics import stringWidth
    import reportlab.platypus.paragraph as rlp

    def thai_word_split(word, maxWidths, fontName, fontSize, encoding='utf8'):
        if not isinstance(maxWidths, (list, tuple)):
            maxWidths = [maxWidths]
        unshaped = unshape_thai(word)
        try:
            tokens_unshaped = pythainlp.word_tokenize(unshaped, engine='newmm', keep_whitespace=True)
        except Exception:
            tokens_unshaped = list(unshaped)

        tokens = [adjust_thai(t) for t in tokens_unshaped]

        lines = []
        line_tokens = []
        current_w = 0.0
        line_idx = 0
        max_w = maxWidths[0]

        for t in tokens:
            tw = stringWidth(t, fontName, fontSize)
            if current_w + tw <= max_w or not line_tokens:
                line_tokens.append(t)
                current_w += tw
            else:
                line_str = ''.join(line_tokens).strip()
                extra = max_w - current_w
                lines.append([extra, line_str])
                line_idx += 1
                max_w = maxWidths[line_idx] if line_idx < len(maxWidths) else maxWidths[-1]
                line_tokens = [t]
                current_w = tw

        if line_tokens:
            line_str = ''.join(line_tokens).strip()
            extra = max_w - current_w
            lines.append([extra, line_str])
        return lines

    def thai_cjkFragSplit(frags, maxWidths, calcBounds, encoding='utf8'):
        all_text = ''
        for frag in frags:
            t = frag.text
            if rlp.isBytes(t):
                t = t.decode(encoding)
            all_text += t

        unshaped = unshape_thai(all_text)
        try:
            tokens = pythainlp.word_tokenize(unshaped, engine='newmm', keep_whitespace=True)
        except Exception:
            tokens = list(unshaped)

        boundaries = set()
        pos = 0
        for tok in tokens:
            pos += len(tok)
            boundaries.add(pos)

        U = []
        for frag in frags:
            text = frag.text
            if rlp.isBytes(text):
                text = text.decode(encoding)
            shaped_text = adjust_thai(text)
            if shaped_text:
                U.extend([rlp.cjkU(t, frag, encoding) for t in shaped_text])
            else:
                U.append(rlp.cjkU(shaped_text, frag, encoding))

        lines = []
        i = widthUsed = lineStartPos = 0
        maxWidth = maxWidths[0]
        nU = len(U)
        while i < nU:
            u = U[i]
            i += 1
            w = u.width
            if hasattr(w, 'normalizedValue'):
                w._normalizer = maxWidth
                w = w.normalizedValue(maxWidth)
            widthUsed += w
            lineBreak = hasattr(u.frag, 'lineBreak')
            endLine = (widthUsed > maxWidth + rlp._FUZZ and widthUsed > 0) or lineBreak
            if endLine:
                extraSpace = maxWidth - widthUsed
                if not lineBreak:
                    best_split = None
                    for j in range(i - 1, lineStartPos, -1):
                        if j in boundaries or (j < len(U) and U[j] and rlp.category(U[j]) == 'Zs'):
                            best_split = j
                            break
                    if best_split is not None and best_split > lineStartPos:
                        excess_w = sum(U[k].width for k in range(best_split, i))
                        extraSpace += excess_w
                        i = best_split
                    elif u not in rlp.ALL_CANNOT_START and i > lineStartPos + 1:
                        i -= 1
                        extraSpace += w
                lines.append(rlp.makeCJKParaLine(U[lineStartPos:i], maxWidth, widthUsed, extraSpace, lineBreak, calcBounds))
                try:
                    maxWidth = maxWidths[len(lines)]
                except IndexError:
                    maxWidth = maxWidths[-1]
                lineStartPos = i
                widthUsed = 0

        if widthUsed > 0:
            lines.append(rlp.makeCJKParaLine(U[lineStartPos:], maxWidth, widthUsed, maxWidth - widthUsed, False, calcBounds))
        return rlp.ParaLines(kind=1, lines=lines)

    rlp.wordSplit = thai_word_split
    rlp.cjkFragSplit = thai_cjkFragSplit
    _wrapped_patched = True



def _styles() -> dict[str, ParagraphStyle]:
    """นิยามรูปแบบข้อความทั้งหมดของเอกสารตามหลักวิชาการ (ขนาดมาตรฐาน TH Sarabun New 16pt / สีดำล้วน)"""
    base = getSampleStyleSheet()['Normal']
    s: dict[str, ParagraphStyle] = {}

    s['body'] = ParagraphStyle(
        'body', parent=base, fontName=FONT_REGULAR, fontSize=16,
        leading=23, alignment=TA_LEFT, spaceAfter=8,
        wordWrap='CJK', textColor=diagrams.INK)
    s['body_indent'] = ParagraphStyle(
        'body_indent', parent=s['body'], firstLineIndent=36, spaceAfter=8)
    s['h1'] = ParagraphStyle(
        'h1', parent=base, fontName=FONT_BOLD, fontSize=18, leading=26,
        spaceBefore=16, spaceAfter=14, alignment=TA_CENTER, textColor=diagrams.INK,
        keepWithNext=True)
    s['h2'] = ParagraphStyle(
        'h2', parent=base, fontName=FONT_BOLD, fontSize=16, leading=23,
        spaceBefore=14, spaceAfter=8, textColor=diagrams.INK,
        keepWithNext=True)
    s['h3'] = ParagraphStyle(
        'h3', parent=base, fontName=FONT_BOLD, fontSize=16, leading=23,
        spaceBefore=10, spaceAfter=6, textColor=diagrams.INK,
        keepWithNext=True)
    s['bullet'] = ParagraphStyle(
        'bullet', parent=s['body'], leftIndent=24, bulletIndent=10,
        spaceAfter=4, alignment=TA_LEFT, wordWrap='CJK')
    s['td'] = ParagraphStyle(
        'td', parent=base, fontName=FONT_REGULAR, fontSize=13, leading=17.5,
        wordWrap='CJK', textColor=diagrams.INK)
    s['th'] = ParagraphStyle(
        'th', parent=base, fontName=FONT_BOLD, fontSize=13.5, leading=18,
        wordWrap='CJK', textColor=diagrams.INK)
    s['caption'] = ParagraphStyle(
        'caption', parent=base, fontName=FONT_BOLD, fontSize=14,
        leading=20, alignment=TA_CENTER, textColor=diagrams.INK,
        spaceBefore=6, spaceAfter=14)
    s['table_caption'] = ParagraphStyle(
        'table_caption', parent=base, fontName=FONT_BOLD, fontSize=15,
        leading=21, alignment=TA_LEFT, textColor=diagrams.INK,
        spaceBefore=10, spaceAfter=5, keepWithNext=False)
    s['ref_item'] = ParagraphStyle(
        'ref_item', parent=base, fontName=FONT_REGULAR, fontSize=15,
        leading=22, leftIndent=28, firstLineIndent=-28,
        spaceAfter=6, wordWrap='CJK', textColor=diagrams.INK)
    s['td_mono'] = ParagraphStyle(
        'td_mono', parent=s['td'], fontSize=12, leading=16)
    s['note'] = ParagraphStyle(
        'note', parent=base, fontName=FONT_REGULAR, fontSize=14,
        leading=20, textColor=diagrams.INK)

    # สไตล์สำหรับหน้าปกและหน้าอนุมัติ (สีดำล้วน)
    s['cover_institution'] = ParagraphStyle(
        'cover_institution', parent=base, fontName=FONT_BOLD, fontSize=16,
        leading=23, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_report_type'] = ParagraphStyle(
        'cover_report_type', parent=base, fontName=FONT_BOLD, fontSize=16,
        leading=23, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_title'] = ParagraphStyle(
        'cover_title', parent=base, fontName=FONT_BOLD, fontSize=20,
        leading=28, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_title_en'] = ParagraphStyle(
        'cover_title_en', parent=base, fontName=FONT_BOLD, fontSize=15,
        leading=21, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_project'] = ParagraphStyle(
        'cover_project', parent=base, fontName=FONT_BOLD, fontSize=17,
        leading=24, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_sub'] = ParagraphStyle(
        'cover_sub', parent=base, fontName=FONT_REGULAR, fontSize=15,
        leading=21, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_meta'] = ParagraphStyle(
        'cover_meta', parent=base, fontName=FONT_REGULAR, fontSize=15,
        leading=22, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_meta_bold'] = ParagraphStyle(
        'cover_meta_bold', parent=base, fontName=FONT_BOLD, fontSize=15,
        leading=22, alignment=TA_CENTER, textColor=diagrams.INK)

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
        is_major = not num or num.startswith('บทที่') or num.startswith('ภาค') or num in ('บทคัดย่อ', 'เอกสารอ้างอิง') or title in ('สารบัญเนื้อหา', 'สารบัญตาราง', 'สารบัญภาพ', 'เอกสารอ้างอิงและบรรณานุกรม')
        cell_style = s['td']
        num_text = f'<b>{esc(num)}</b>' if is_major and num else esc(num)
        title_text = f'<b>{esc(title)}</b>' if is_major else f'&nbsp;&nbsp;&nbsp;&nbsp;{esc(title)}'
        rows.append([
            Paragraph(num_text, cell_style),
            Paragraph(title_text, cell_style),
            Paragraph(str(page), cell_style),
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


def _figure(drawing_or_img, caption: str, styles: dict, anchor: Flowable | None = None) -> list:
    """ฝังไดอะแกรมเวกเตอร์ หรือ ภาพหน้าจอระบบ + คำบรรยายใต้ภาพ (ผูกติดกันด้วย KeepTogether เพื่อไม่ให้แยกหน้า)"""
    s = styles
    elements = []
    if anchor:
        elements.append(anchor)

    if isinstance(drawing_or_img, (str, Path)):
        img_path = str(drawing_or_img)
        if not os.path.exists(img_path):
            return elements

        with PILImage.open(img_path) as pil_im:
            w_px, h_px = pil_im.size
        aspect = h_px / w_px
        target_w = min(CONTENT_W, 145 * mm)
        target_h = target_w * aspect
        # จำกัดความสูงไม่ให้เกิน 88 มม. เพื่อให้จัดวางร่วมกับข้อความในหน้าได้อย่างลงตัว
        if target_h > 88 * mm:
            target_h = 88 * mm
            target_w = target_h / aspect

        img = Image(img_path, width=target_w, height=target_h)
        img_table = Table([[img]], colWidths=[target_w])
        img_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bbbbbb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.extend([
            Spacer(1, 4),
            img_table,
            Spacer(1, 3),
            Paragraph(esc(caption), s['caption']),
            Spacer(1, 6),
        ])
    else:
        scale = min(1.0, CONTENT_W / drawing_or_img.width)
        img = Image(drawing_or_img, width=drawing_or_img.width * scale,
                    height=drawing_or_img.height * scale)
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
    # ป้องกันคำอธิบายหัวตารางตกค้างเดี่ยว ๆ ท้ายหน้า ถ้าพื้นที่เหลือน้อยกว่า 50 มม. ให้ยกไปหน้าถัดไปพร้อมหัวตาราง
    flowables.append(CondPageBreak(50 * mm))
    if anchor:
        flowables.append(anchor)
    if 'title' in spec and spec['title']:
        flowables.append(Paragraph(esc(spec['title']), s['table_caption']))

    head_cols = len(spec['head'])
    if widths is None:
        if head_cols == 2:
            widths = [CONTENT_W * 0.35, CONTENT_W * 0.65]
        elif head_cols == 3:
            h0 = str(spec['head'][0])
            if 'บทบาท' in h0:
                widths = [CONTENT_W * 0.25, CONTENT_W * 0.38, CONTENT_W * 0.37]
            elif 'ด้าน' in h0:
                widths = [CONTENT_W * 0.24, CONTENT_W * 0.40, CONTENT_W * 0.36]
            else:
                widths = [CONTENT_W * 0.25, CONTENT_W * 0.40, CONTENT_W * 0.35]
        elif head_cols == 4:
            widths = [CONTENT_W * 0.16, CONTENT_W * 0.26, CONTENT_W * 0.28, CONTENT_W * 0.30]
        elif head_cols == 6:
            widths = [31 * mm, 21 * mm, 24 * mm, 24 * mm, 26 * mm, CONTENT_W - 126 * mm]

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
    if 'title' in spec and spec['title'] and len(spec['rows']) <= 3:
        return [KeepTogether(flowables)]
    return flowables


def _block_renderer(blocks, styles: dict, page_registry: dict | None = None) -> list:
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
            out.append(Paragraph('ตารางที่ 5.1 สาระสำคัญของการทดสอบระบบ (Test Focus)', s['table_caption']))
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
        elif kind == 'image':
            img_path = block[1]
            caption = block[2] if len(block) > 2 else ''
            anchor_obj = PageAnchor('fig_app_1', page_registry) if (page_registry and 'ก.1' in caption) else None
            if os.path.exists(img_path):
                out.extend(_figure(img_path, caption, s, anchor=anchor_obj))
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
        canvas.setFont(FONT_REGULAR, 14)
        canvas.setFillColor(diagrams.INK)
        p = canvas.getPageNumber() - 2  # หักหน้าปก 1 หน้าออก -> หน้าที่ 2 คือ ก
        label = THAI_NUMERALS[p] if 0 <= p < len(THAI_NUMERALS) else str(p + 1)
        canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 12, label)
        canvas.restoreState()

    def on_chapter_first(canvas, _doc):
        # หน้าแรกของแต่ละบท: ไม่พิมพ์เลขหน้าและไม่มีหัวกระดาษตามมาตรฐานวิชาการ
        pass

    def on_chapter_body(canvas, _doc):
        # หน้าเนื้อหาทั่วไป: แสดงเฉพาะเลขหน้าอารบิกมุมบนขวาตามมาตรฐานวิชาการ
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 14)
        canvas.setFillColor(diagrams.INK)
        arabic_page = canvas.getPageNumber() - main_start_box[0] + 1
        canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 12, str(arabic_page))
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[frame], onPage=on_cover),
        PageTemplate(id='prelim', frames=[frame], onPage=on_prelim),
        PageTemplate(id='chapter_first', frames=[frame], onPage=on_chapter_first),
        PageTemplate(id='chapter_body', frames=[frame], onPage=on_chapter_body),
    ])
    return doc


def _default_screenshots_pack() -> dict[str, tuple[str, str]]:
    from django.conf import settings
    sc_dir = Path(settings.BASE_DIR) / 'docs' / 'screenshots'
    return {
        'fig_4_1': (str(sc_dir / '01_home_catalog.png'),
                    'ภาพที่ 4.1 หน้าแรกและแคตตาล็อกสินค้าพร้อมการค้นหาสด (Home & Product Catalog)'),
        'fig_4_2': (str(sc_dir / '02_product_detail.png'),
                    'ภาพที่ 4.2 หน้ารายละเอียดสินค้า ข้อมูลทางเทคนิค และสต็อกคงเหลือ (Product Detail & Specifications)'),
        'fig_4_3': (str(sc_dir / '03_cart_checkout.png'),
                    'ภาพที่ 4.3 ตะกร้าสินค้าและการสรุปรายการก่อนสั่งซื้อ (Cart & Checkout Review)'),
        'fig_4_4': (str(sc_dir / '04_order_tracking.png'),
                    'ภาพที่ 4.4 หน้าติดตามคำสั่งซื้อ บันไดสถานะ 4 ขั้น และประวัติการแจ้งปัญหา (Order Tracking & Issue History)'),
        'fig_4_5': (str(sc_dir / '05_customer_account.png'),
                    'ภาพที่ 4.5 หน้าบัญชีลูกค้า ประวัติการสั่งซื้อ และสมุดที่อยู่จัดส่ง (Customer Account & Orders)'),
        'fig_4_6': (str(sc_dir / '06_staff_orders.png'),
                    'ภาพที่ 4.6 ตารางจัดการคำสั่งซื้อพร้อมระบบแจ้งเตือนปัญหา (Staff Orders Management)'),
        'fig_4_7': (str(sc_dir / '07_staff_order_detail.png'),
                    'ภาพที่ 4.7 หน้ารายละเอียดคำสั่งซื้อ ข้อมูลการชำระเงิน และการจัดการสถานะ (Staff Order Detail & Actions)'),
        'fig_4_8': (str(sc_dir / '08_staff_issues.png'),
                    'ภาพที่ 4.8 ศูนย์จัดการปัญหาคำสั่งซื้อและข้อร้องเรียนของลูกค้า (Staff Order Issues Center)'),
        'fig_4_9': (str(sc_dir / '09_staff_dashboard.png'),
                    'ภาพที่ 4.9 แดชบอร์ดสรุปยอดขาย การวิเคราะห์ และตัวชี้วัดประสิทธิภาพ (Sales Analytics Dashboard)'),
        'fig_4_10': (str(sc_dir / '10_staff_employees.png'),
                     'ภาพที่ 4.10 หน้าจัดการข้อมูลพนักงานและการสืบค้นสด (Staff Directory & Live Search)'),
    }


def _build_story(meta: dict, chapters: list[dict], diagrams_pack: dict,
                 appendix_blocks: list[dict], current_chapter: list[str],
                 page_registry: dict[str, int], main_start_box: list[int],
                 screenshots_pack: dict | None = None,
                 is_pass2: bool = False) -> list:
    """สร้าง Story ทั้งเล่มรายงาน พร้อมจัดลำดับ Template สอดคล้องตามหลักวิชาการ"""
    styles = _styles()
    story: list = []
    if screenshots_pack is None:
        screenshots_pack = _default_screenshots_pack()

    # 1. หน้าปกรายงาน (Report Cover) -> Template: cover
    story += _cover(meta)
    story.append(NextPageTemplate('prelim'))
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
        idx = raw_p - 2  # ปก = หน้า 1 -> หน้า 2 คือ ก
        return THAI_NUMERALS[idx] if 0 <= idx < len(THAI_NUMERALS) else str(idx + 1)

    # 2. ส่วนนำ -> Template: prelim (สารบัญเนื้อหา สารบัญตาราง สารบัญภาพ)
    # 2.1 สารบัญเนื้อหา (Table of Contents)
    story.append(PageAnchor('toc', page_registry))
    toc_entries = [
        ('', 'สารบัญเนื้อหา', p_prelim('toc', 'ก')),
        ('', 'สารบัญตาราง', p_prelim('lot', 'ค')),
        ('', 'สารบัญภาพ', p_prelim('lof', 'ง')),
        ('บทที่ 1', 'บทนำ', p_num('ch_intro', 1)),
        ('1.1', 'ความเป็นมาและความสำคัญของโครงงาน', p_num('sec_1_1', 1)),
        ('1.2', 'วัตถุประสงค์ของโครงงาน', p_num('sec_1_2', 1)),
        ('1.3', 'ขอบเขตของระบบงาน', p_num('sec_1_3', 2)),
        ('1.4', 'ประโยชน์ที่คาดว่าจะได้รับ', p_num('sec_1_4', 3)),
        ('บทที่ 2', 'การวิเคราะห์และออกแบบระบบ', p_num('ch_analysis', 4)),
        ('2.1', 'การวิเคราะห์ความต้องการของระบบ (Requirements Analysis)', p_num('sec_2_1', 4)),
        ('2.2', 'การออกแบบกรณีการใช้งานและกลุ่มผู้ใช้ (Use Case & Actor Analysis)', p_num('sec_2_2', 5)),
        ('2.3', 'การออกแบบสถาปัตยกรรมระบบ 4 ชั้น (4-Layer Clean Architecture)', p_num('sec_2_3', 6)),
        ('2.4', 'การออกแบบแบบจำลองข้อมูลและความสัมพันธ์ (Data Modeling & ERD)', p_num('sec_2_4', 7)),
        ('2.5', 'เมทริกซ์ความสัมพันธ์และกฎเกณฑ์ความคงสภาพ (Relationship Matrix)', p_num('sec_2_5', 8)),
        ('2.6', 'การออกแบบเครื่องจักรสถานะคำสั่งซื้อ (Order Lifecycle State Machine)', p_num('sec_2_6', 9)),
        ('บทที่ 3', 'การพัฒนาระบบ', p_num('ch_development', 10)),
        ('3.1', 'สภาพแวดล้อมและเทคโนโลยีที่ใช้ในการพัฒนาระบบ (Technology Stack & Tools)', p_num('sec_3_1', 10)),
        ('3.2', 'โครงสร้างโปรเจกต์และโมดูลระบบ (Project Directory Structure)', p_num('sec_3_2', 11)),
        ('3.3', 'สถาปัตยกรรมส่วนต่อประสาน 2 โซน (Dual-Zone Architecture)', p_num('sec_3_3', 12)),
        ('3.4', 'การพัฒนาระบบการเงินและจุดรับเงินจุดเดียว (Single Point of Payment Entry)', p_num('sec_3_4', 13)),
        ('3.5', 'การพัฒนาระบบการแจ้งปัญหาและข้อร้องเรียนของลูกค้า (Order Issue Resolution)', p_num('sec_3_5', 14)),
        ('3.6', 'ระบบบันทึกประวัติการทำงานแบบเพิ่มต่อท้าย (Append-Only Audit Trail)', p_num('sec_3_6', 15)),
        ('3.7', 'การรักษาความมั่นคงปลอดภัยของระบบ (System Security & RBAC)', p_num('sec_3_7', 16)),
        ('บทที่ 4', 'ผลการพัฒนาและภาพหน้าจอระบบ', p_num('ch_results', 17)),
        ('4.1', 'ผลการพัฒนาส่วนต่อประสานสำหรับลูกค้า (Customer Storefront Zone)', p_num('sec_4_1', 17)),
        ('4.2', 'ผลการพัฒนาส่วนต่อประสานสำหรับเจ้าหน้าที่ (Staff Management Zone)', p_num('sec_4_2', 20)),
        ('บทที่ 5', 'การทดสอบและสรุปผล', p_num('ch_conclusion', 23)),
        ('5.1', 'ระเบียบวิธีและกลยุทธ์การทดสอบอัตโนมัติ', p_num('sec_5_1', 23)),
        ('5.2', 'สาระสำคัญของการทดสอบระบบ', p_num('sec_5_2', 24)),
        ('5.3', f'สรุปผลการรันชุดทดสอบอัตโนมัติ ({TOTAL_TESTS} Test Cases)', p_num('sec_5_3', 25)),
        ('5.4', 'สรุปผลการดำเนินงานโครงงาน', p_num('sec_5_4', 25)),
        ('5.5', 'ปัญหา อุปสรรค และแนวทางการแก้ไข', p_num('sec_5_5', 26)),
        ('5.6', 'ข้อจำกัดและข้อเสนอแนะในการพัฒนาต่อยอด', p_num('sec_5_6', 27)),
        ('', 'เอกสารอ้างอิงและบรรณานุกรม', p_num('ch_references', 28)),
        ('ภาคผนวก ก', 'ข้อมูลการเข้าใช้งานระบบและแหล่งเก็บรหัสต้นฉบับ', p_num('ch_app_a', 29)),
        ('ภาคผนวก ข', 'คู่มือการใช้งานระบบโดยย่อ', p_num('ch_app_b', 31)),
        ('ภาคผนวก ค', 'พจนานุกรมข้อมูลและโครงสร้างระบบ', p_num('ch_app_c', 33)),
        ('ภาคผนวก ง', 'ประวัติผู้จัดทำโครงงาน', p_num('ch_app_d', 42)),
    ]
    story += _toc(toc_entries)
    story.append(PageBreak())

    # 2.2 สารบัญตาราง (List of Tables)
    story.append(PageAnchor('lot', page_registry))
    lot_entries = [
        ('ตารางที่ 1.1', 'ขอบเขตของโครงการ', p_num('tab_1_1', 2)),
        ('ตารางที่ 2.1', 'ประเภทผู้ใช้งานและระดับสิทธิ์ในระบบ (User Roles & Access Levels)', p_num('tab_2_1', 5)),
        ('ตารางที่ 2.2', 'เมทริกซ์ความสัมพันธ์ของเอนทิตีและกฎเกณฑ์ความคงสภาพ', p_num('tab_2_2', 8)),
        ('ตารางที่ 5.1', 'สาระสำคัญของการทดสอบระบบ (Test Focus)', p_num('tab_5_1', 24)),
        ('ตารางที่ 5.2', 'สรุปผลการประเมินชุดการทดสอบอัตโนมัติ', p_num('tab_5_2', 25)),
        ('ตารางที่ 5.3', 'ปัญหา อุปสรรค และแนวทางการแก้ไข', p_num('tab_5_3', 26)),
        ('ตารางที่ 5.4', 'ข้อจำกัดของระบบในปัจจุบัน', p_num('tab_5_4', 27)),
        ('ตารางที่ ก.1', 'ข้อมูลแหล่งเข้าถึงระบบและรหัสต้นฉบับ', p_num('tab_app_1', 29)),
        ('ตารางที่ ก.2', 'บัญชีผู้ใช้สำหรับการทดสอบระบบ (Test Accounts)', p_num('tab_app_2', 30)),
    ]
    story += _lot(lot_entries)
    story.append(PageBreak())

    # 2.3 สารบัญภาพ (List of Figures)
    story.append(PageAnchor('lof', page_registry))
    lof_entries = [
        ('ภาพที่ 2.1', 'แผนภาพกรณีการใช้งานของระบบ (Use Case Diagram)', p_num('fig_2_1', 6)),
        ('ภาพที่ 2.2', 'แผนภาพสถาปัตยกรรมระบบแบบ 4 ชั้น (4-Layer System Architecture)', p_num('fig_2_2', 7)),
        ('ภาพที่ 2.3', 'แผนภาพความสัมพันธ์ข้อมูล (Entity-Relationship Diagram - ERD)', p_num('fig_2_3', 8)),
        ('ภาพที่ 2.4', 'แผนผังวงจรชีวิตสถานะคำสั่งซื้อ (Order Lifecycle State Transition)', p_num('fig_2_4', 10)),
        ('ภาพที่ 4.1', 'หน้าแรกและแคตตาล็อกสินค้าพร้อมการค้นหาสด (Home & Product Catalog)', p_num('fig_4_1', 17)),
        ('ภาพที่ 4.2', 'หน้ารายละเอียดสินค้า ข้อมูลทางเทคนิค และสต็อกคงเหลือ (Product Detail & Specs)', p_num('fig_4_2', 17)),
        ('ภาพที่ 4.3', 'ตะกร้าสินค้าและการสรุปรายการก่อนสั่งซื้อ (Cart & Checkout Review)', p_num('fig_4_3', 18)),
        ('ภาพที่ 4.4', 'หน้าติดตามคำสั่งซื้อและประวัติการแจ้งปัญหา (Order Tracking & Issue History)', p_num('fig_4_4', 18)),
        ('ภาพที่ 4.5', 'หน้าบัญชีลูกค้าและประวัติการสั่งซื้อ (Customer Account & Orders)', p_num('fig_4_5', 19)),
        ('ภาพที่ 4.6', 'ตารางจัดการคำสั่งซื้อพร้อมระบบแจ้งเตือนปัญหา (Staff Orders Management)', p_num('fig_4_6', 20)),
        ('ภาพที่ 4.7', 'หน้ารายละเอียดคำสั่งซื้อ ข้อมูลการชำระเงิน และการจัดการสถานะ (Staff Order Detail)', p_num('fig_4_7', 20)),
        ('ภาพที่ 4.8', 'ศูนย์จัดการปัญหาคำสั่งซื้อและข้อร้องเรียนของลูกค้า (Staff Order Issues Center)', p_num('fig_4_8', 21)),
        ('ภาพที่ 4.9', 'แดชบอร์ดสรุปยอดขาย การวิเคราะห์ และตัวชี้วัดประสิทธิภาพ (Sales Analytics Dashboard)', p_num('fig_4_9', 21)),
        ('ภาพที่ 4.10', 'หน้าจัดการข้อมูลพนักงานและการสืบค้นสด (Staff Directory & Live Search)', p_num('fig_4_10', 22)),
        ('ภาพผนวกที่ ก.1', 'QR Code สำหรับเข้าสู่ระบบ THAMMATHAD SHOP', p_num('fig_app_1', 29)),
    ]
    story += _lof(lof_entries)
    # เตรียมเปลี่ยนเป็น 'chapter_first' สำหรับหน้าแรกของบทที่ 1
    story.append(NextPageTemplate('chapter_first'))
    story.append(PageBreak())

    # 3. ส่วนเนื้อหาหลัก 5 บท + เอกสารอ้างอิง: เริ่มนับหน้า 1
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
                elif '3.7' in title_text: story.append(PageAnchor('sec_3_7', page_registry))
                elif '4.1' in title_text: story.append(PageAnchor('sec_4_1', page_registry))
                elif '4.2' in title_text: story.append(PageAnchor('sec_4_2', page_registry))
                elif '5.1' in title_text: story.append(PageAnchor('sec_5_1', page_registry))
                elif '5.2' in title_text: story.append(PageAnchor('sec_5_2', page_registry))
                elif '5.3' in title_text: story.append(PageAnchor('sec_5_3', page_registry))
                elif '5.4' in title_text: story.append(PageAnchor('sec_5_4', page_registry))
                elif '5.5' in title_text: story.append(PageAnchor('sec_5_5', page_registry))
                elif '5.6' in title_text: story.append(PageAnchor('sec_5_6', page_registry))

            if kind == 'table':
                t_title = block[1].get('title', '')
                t_str = str(block[1])
                anchor_key = None
                if '1.1' in t_title or 'ด้านขอบเขต' in t_str:
                    anchor_key = 'tab_1_1'
                elif '2.1' in t_title or 'ประเภทผู้ใช้งาน' in t_str or 'บทบาทผู้ใช้งาน' in t_str:
                    anchor_key = 'tab_2_1'
                elif '2.2' in t_title or 'เมทริกซ์' in t_str:
                    anchor_key = 'tab_2_2'
                elif '5.2' in t_title or 'สรุปผลการประเมิน' in t_str:
                    anchor_key = 'tab_5_2'
                elif '5.3' in t_title or 'ปัญหา / อุปสรรค' in t_str or 'ปัญหา อุปสรรค' in t_str:
                    anchor_key = 'tab_5_3'
                elif '5.4' in t_title or 'ข้อจำกัด' in t_str:
                    anchor_key = 'tab_5_4'

                anchor_obj = PageAnchor(anchor_key, page_registry) if anchor_key else None
                story += _data_table(block[1], styles, anchor=anchor_obj)
                story.append(Spacer(1, 10))
                continue

            if kind == 'focus':
                anchor_obj = PageAnchor('tab_5_1', page_registry)
                focus_flowables = [
                    anchor_obj,
                    Paragraph('ตารางที่ 5.1 สาระสำคัญของการทดสอบระบบ (Test Focus)', styles['table_caption'])
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

            story += _block_renderer([block], styles, page_registry)

            # ฝังไดอะแกรมเวกเตอร์ในบทที่ 2 ให้สอดคล้องกับเนื้อหา (วางต่อจากย่อหน้าที่อ้างอิงถึงภาพ)
            if ch_id == 'analysis' and kind == 'p':
                if 'ภาพที่ 2.1' in block[1] and 'usecase' in diagrams_pack:
                    d, cap = diagrams_pack['usecase']
                    anchor_obj = PageAnchor('fig_2_1', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif 'ภาพที่ 2.2' in block[1] and 'layered' in diagrams_pack:
                    d, cap = diagrams_pack['layered']
                    anchor_obj = PageAnchor('fig_2_2', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif 'ภาพที่ 2.3' in block[1] and 'er' in diagrams_pack:
                    d, cap = diagrams_pack['er']
                    anchor_obj = PageAnchor('fig_2_3', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)
                elif 'ภาพที่ 2.4' in block[1] and 'lifecycle' in diagrams_pack:
                    d, cap = diagrams_pack['lifecycle']
                    anchor_obj = PageAnchor('fig_2_4', page_registry)
                    story += _figure(d, cap, styles, anchor=anchor_obj)

            # ฝังภาพหน้าจอระบบในบทที่ 4 ตามหัวข้อย่อย
            if ch_id == 'results' and kind == 'p':
                if '1. หน้าแรกและแคตตาล็อกสินค้า' in block[1]:
                    for fig_k in ('fig_4_1', 'fig_4_2', 'fig_4_3', 'fig_4_4', 'fig_4_5'):
                        if fig_k in screenshots_pack:
                            img_f, cap = screenshots_pack[fig_k]
                            anchor_obj = PageAnchor(fig_k, page_registry)
                            story += _figure(img_f, cap, styles, anchor=anchor_obj)
                elif '1. ตารางจัดการคำสั่งซื้อ' in block[1]:
                    for fig_k in ('fig_4_6', 'fig_4_7', 'fig_4_8', 'fig_4_9', 'fig_4_10'):
                        if fig_k in screenshots_pack:
                            img_f, cap = screenshots_pack[fig_k]
                            anchor_obj = PageAnchor(fig_k, page_registry)
                            story += _figure(img_f, cap, styles, anchor=anchor_obj)

        # ก่อนจบบท เตรียมเปลี่ยนหน้าใหม่เป็น 'chapter_first'
        story.append(NextPageTemplate('chapter_first'))
        story.append(PageBreak())

    # 4. เอกสารอ้างอิงและบรรณานุกรม
    from .content import REFERENCES
    if REFERENCES:
        story.append(PageAnchor('ch_references', page_registry))
        story.append(_ChapterMarker('เอกสารอ้างอิงและบรรณานุกรม', current_chapter))
        story.append(Paragraph('เอกสารอ้างอิงและบรรณานุกรม', styles['h1']))
        story.append(Spacer(1, 4 * mm))
        story.append(NextPageTemplate('chapter_body'))
        story += _block_renderer(REFERENCES, styles, page_registry)
        story.append(NextPageTemplate('chapter_first'))
        story.append(PageBreak())

    # 5. ภาคผนวก 4 ชุด
    if appendix_blocks:
        first_app = True
        for block in appendix_blocks:
            kind = block[0]
            if kind == 'h2' and 'ภาคผนวก' in block[1]:
                app_title = block[1]
                app_key = 'ch_app_a'
                if 'ภาคผนวก ข' in app_title:
                    app_key = 'ch_app_b'
                elif 'ภาคผนวก ค' in app_title:
                    app_key = 'ch_app_c'
                elif 'ภาคผนวก ง' in app_title:
                    app_key = 'ch_app_d'

                story.append(NextPageTemplate('chapter_first'))
                if not first_app:
                    story.append(PageBreak())
                first_app = False
                story.append(PageAnchor(app_key, page_registry))
                story.append(_ChapterMarker(app_title, current_chapter))
                story.append(Paragraph(esc(app_title), styles['h1']))
                story.append(Spacer(1, 4 * mm))
                story.append(NextPageTemplate('chapter_body'))
                continue

            if kind == 'table':
                t_title = block[1].get('title', '')
                t_str = str(block[1])
                anchor_key = None
                if 'ก.1' in t_title or 'แหล่งเข้าถึงระบบ' in t_str:
                    anchor_key = 'tab_app_1'
                elif 'ก.2' in t_title or 'บัญชีผู้ใช้สำหรับการทดสอบ' in t_str:
                    anchor_key = 'tab_app_2'

                anchor_obj = PageAnchor(anchor_key, page_registry) if anchor_key else None
                story += _data_table(block[1], styles, anchor=anchor_obj)
                story.append(Spacer(1, 10))
                continue

            story += _block_renderer([block], styles, page_registry)

    return story


def build_pdf(target: str, meta: dict, chapters: list[dict], diagrams_pack: dict,
              appendix_blocks: list[dict], screenshots_pack: dict | None = None) -> str:
    """ประกอบเอกสารรายงาน PDF เชิงวิชาการทั้งเล่ม (Two-Pass Page Numbering)"""
    _install_thai_word_wrap()
    diagrams.register_thai_fonts()
    if screenshots_pack is None:
        screenshots_pack = _default_screenshots_pack()

    # Pass 1: บันทึกเลขหน้าจริงของแต่ละส่วนลงใน page_registry
    page_registry: dict[str, int] = {}
    current_chapter: list[str] = ['']
    main_start_box: list[int] = [0]

    dummy_target = io.BytesIO()
    doc1 = _create_doc_templates(dummy_target, meta, current_chapter, main_start_box)
    story1 = _build_story(meta, chapters, diagrams_pack, appendix_blocks,
                          current_chapter, page_registry, main_start_box,
                          screenshots_pack=screenshots_pack, is_pass2=False)
    doc1.build(story1)

    # กำหนดหมายเลขหน้าที่บทที่ 1 เริ่มต้น (เพื่อใช้คำนวณเลขอารบิก)
    main_start_page = page_registry.get('ch_intro', 5)
    main_start_box[0] = main_start_page

    # Pass 2: สร้างเอกสารฉบับสมบูรณ์พร้อมเลขหน้าจริงในสารบัญ
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    current_chapter = ['']
    doc2 = _create_doc_templates(target, meta, current_chapter, main_start_box)
    story2 = _build_story(meta, chapters, diagrams_pack, appendix_blocks,
                          current_chapter, page_registry, main_start_box,
                          screenshots_pack=screenshots_pack, is_pass2=True)
    doc2.build(story2)

    return target
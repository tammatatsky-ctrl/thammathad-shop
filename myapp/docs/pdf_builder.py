"""สร้างเอกสารรายงานเป็น PDF (reportlab platypus)

ไดอะแกรมฝังเป็น **vector** (ไม่ใช่ภาพบิตแมป) จึงพิมพ์คมชัดที่ความละเอียด
ใด ๆ และผู้ใช้ย่อ/ขยายใน Adobe Reader ได้โดยไม่เบลอ

ทุกอย่างที่พิมพ์ผ่าน `facts.py` จึงตรงกับโค้ดเสมอ ถ้าเพิ่มโมเดลหรือ URL
แล้วรันคำสั่งซ้ำ ตัวเลขในเอกสารจะเปลี่ยนตาม
"""

from __future__ import annotations

import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from . import diagrams
from .diagrams import FONT_BOLD, FONT_REGULAR


PAGE_W, PAGE_H = A4
MARGIN = 22 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _styles() -> dict[str, ParagraphStyle]:
    """นิยามรูปแบบข้อความทั้งหมดของเอกสาร"""
    base = getSampleStyleSheet()['Normal']
    s: dict[str, ParagraphStyle] = {}

    # หมายเหตุเรื่องการจัดวาง: ตั้งใจ **ไม่ justify** ข้อความไทย
    # เพราะภาษาไทยไม่มีช่องว่างระหว่างคำ reportlab จะยืดช่องว่างที่มี
    # (เช่นหลังประโยค) ให้เต็มความกว้างบรรทัด ผลคือหน้าที่มีช่องว่างน้อย
    # จะดูมีคำห่างกันหวือเป็นช่องกว้างปริศนา ซึ่งอ่านยากกว่าจัดซ้าย
    # (หน้าเว็บใช้หลักการเดียวกัน — ดู `.text` ใน theme.css)
    # `wordWrap='CJK'` บังคับให้ตัดบรรทัดได้ที่ทุกอักขระ ไม่ใช่เฉพาะช่องว่าง
    # จำเป็นสำหรับภาษาไทยโดยเฉพาะ: ภาษาไทยไม่มีช่องว่างระหว่างคำ
    # ถ้าใช้โหมดปกติ reportlab จะตัดได้แค่ตรงที่มีช่องว่าง (เช่น หลังประโยค)
    # ผลคือบรรทัดสั้นลงเรื่อย ๆ และมีช่องว่างขาวใหญ่ท้ายบรรทัด
    # (ค่าเริ่มต้นของ reportlab คือ 'CJK' อยู่แล้ว แต่กำหนดให้ชัดเจน
    #  เพื่อให้คนอ่านโค้ดรู้ว่าเป็นการตัดสินใจ ไม่ใช่ค่าเผลอลืม)
    s['body'] = ParagraphStyle(
        'body', parent=base, fontName=FONT_REGULAR, fontSize=10.5,
        leading=18.5, alignment=TA_LEFT, spaceAfter=7,
        wordWrap='CJK', textColor=diagrams.INK)
    s['h1'] = ParagraphStyle(
        'h1', parent=base, fontName=FONT_BOLD, fontSize=17, leading=24,
        spaceBefore=6, spaceAfter=12, textColor=diagrams.INK)
    s['h2'] = ParagraphStyle(
        'h2', parent=base, fontName=FONT_BOLD, fontSize=13, leading=19,
        spaceBefore=14, spaceAfter=7, textColor=diagrams.BLUE)
    s['h3'] = ParagraphStyle(
        'h3', parent=base, fontName=FONT_BOLD, fontSize=11.5, leading=17,
        spaceBefore=10, spaceAfter=5, textColor=diagrams.INK)
    s['bullet'] = ParagraphStyle(
        'bullet', parent=s['body'], leftIndent=16, bulletIndent=5,
        spaceAfter=4, alignment=TA_LEFT, wordWrap='CJK')
    s['td'] = ParagraphStyle(
        'td', parent=base, fontName=FONT_REGULAR, fontSize=9, leading=13.5,
        wordWrap='CJK', textColor=diagrams.INK)
    s['th'] = ParagraphStyle(
        'th', parent=base, fontName=FONT_BOLD, fontSize=9, leading=13,
        wordWrap='CJK', textColor=colors.white)
    s['caption'] = ParagraphStyle(
        'caption', parent=base, fontName=FONT_REGULAR, fontSize=8.6,
        leading=13, alignment=TA_CENTER, textColor=diagrams.MUTED,
        spaceBefore=4, spaceAfter=14)
    s['td_mono'] = ParagraphStyle(
        'td_mono', parent=s['td'], fontSize=8.2)
    s['cover_title'] = ParagraphStyle(
        'cover_title', parent=base, fontName=FONT_BOLD, fontSize=26,
        leading=34, alignment=TA_CENTER, textColor=diagrams.INK)
    s['cover_sub'] = ParagraphStyle(
        'cover_sub', parent=base, fontName=FONT_REGULAR, fontSize=13,
        leading=21, alignment=TA_CENTER, textColor=diagrams.INK_SOFT)
    s['cover_meta'] = ParagraphStyle(
        'cover_meta', parent=base, fontName=FONT_REGULAR, fontSize=11,
        leading=20, alignment=TA_CENTER, textColor=diagrams.MUTED)
    s['note'] = ParagraphStyle(
        'note', parent=base, fontName=FONT_REGULAR, fontSize=9,
        leading=15, textColor=diagrams.AMBER)
    return s


#: ชื่อเรื่องที่ต้อง escape ก่อนส่งเข้า Paragraph (XML ใช้& < > เป็นตัวพิเศษ)
_XML_ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}
_WS = re.compile(r'\s+')
#: แยกย่อหน้าที่คนเขียนเว้นวรรคว่าง (บรรทัดว่างคั่นระหว่างย่อหน้า)
_PARA_SPLIT = re.compile(r'\n[ \t]*\n')


def esc(text: str) -> str:
    """เตรียมข้อความให้พร้อมส่งเข้า `Paragraph`

    นอกจาก escape แล้ว ยัง**ยุบช่องว่างซ้ำและขึ้นบรรทัดใหม่ออก**
    เพราะ reportlab ตีความ `\\n` ในข้อความเป็นการขึ้นบรรทัดใหม่

    เนื้อหาใน `content.py` เขียนคร่อมบรรทัดตามความอ่านง่ายของโค้ด
    ถ้าไม่ยุบขึ้นบรรทัด เอกสารจะแตกบรรทัดตรงตำแหน่งที่สลับโค้ด
    และเว้นวรรคท้ายบรรทัดจะถูกยืดจนดูเหมือนจัดข้อความเต็มสองข้าง
    (เคยเห็นอาการนี้แล้ว — เข้าใจผิดว่าเป็นปัญหาเรื่องการจัดวาง)
    """
    return _WS.sub(' ', ''.join(_XML_ESC.get(c, c) for c in str(text))).strip()


# ---------------------------------------------------------------------------
# ส่วนประกอบ
# ---------------------------------------------------------------------------
def _cover(meta: dict[str, str]) -> list:
    """หน้าปก — เว้นว่างไว้ให้ผู้เรียนกรอกชื่อจริง"""
    s = _styles()
    return [
        Spacer(1, 34 * mm),
        Paragraph('รายงานโครงการวิชาปฏิบัติการ', s['cover_sub']),
        Spacer(1, 6 * mm),
        Paragraph(esc(meta.get('title', '')), s['cover_title']),
        Spacer(1, 4 * mm),
        Paragraph('ระบบร้านค้าออนไลน์อุปกรณ์คอมพิวเตอร์และไอที', s['cover_sub']),
        Spacer(1, 8 * mm),
        Paragraph('THAMMATHAD SHOP', s['cover_meta']),
        Spacer(1, 20 * mm),
    ] + [
        Paragraph(f'{k}: {esc(v) if v else "____________________"}', s['cover_meta'])
        for k, v in meta['student'].items()
    ] + [
        Spacer(1, 6 * mm),
        Paragraph(esc(meta.get('advisor', '')) or 'อาจารย์ที่ปรึกษา: '
                   '____________________', s['cover_meta']),
        Spacer(1, 4 * mm),
        Paragraph(esc(meta.get('year', '')), s['cover_meta']),
        PageBreak(),
    ]


def _toc(entries: list[tuple[str, int, str]]) -> list:
    """สารบัญ (พิมพ์เป็นตาราง — เลขหน้าให้ผู้ใช้เติมเองตอนจัดพิมพ์จริง)"""
    s = _styles()
    rows = [[Paragraph(esc(n), s['td']),
             Paragraph(esc(t), s['td']),
             Paragraph(str(p), s['td'])] for n, p, t in entries]
    table = Table(rows, colWidths=[12 * mm, CONTENT_W - 24 * mm, 12 * mm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor('#e6e9ef')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    return [Paragraph('สารบัญ', s['h1']), table, PageBreak()]


def _figure(drawing, caption: str, styles: dict) -> list:
    """ฝังไดอะแกรม + คำบรรยายใต้ภาพ

    ไดอะแกรมถูกย่อให้พอดีความกว้างเนื้อหาเสมอ — ถ้าไม่ย่อจะล้นขอบกระดาษ
    และถ้าไม่ย่อ/ไม่ขยายเลยกราฟที่กว้างจะเล็กจนอ่านไม่ออก
    """
    s = styles
    scale = min(1.0, CONTENT_W / drawing.width)
    img = Image(drawing, width=drawing.width * scale,
                height=drawing.height * scale)
    return [img, Spacer(1, 3), Paragraph(esc(caption), s['caption'])]


def _data_table(spec: dict, styles: dict, widths=None) -> Table:
    """ตารางจากสเปก {'head': (...), 'rows': [...]}"""
    s = styles
    head = [Paragraph(esc(h), s['th']) for h in spec['head']]
    body = [[Paragraph(esc(c), s['td']) for c in row] for row in spec['rows']]
    table = Table([head] + body, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), diagrams.BLUE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f6f8fb')]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6dae1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table


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
            # แยกย่อหน้าที่คนเขียนเว้นวรรคว่างไว้เป็นย่อหน้าจริง
            # ถ้ายุบช่องว่างรวมเป็นข้อความเดียว เนื้อหาสองย่อหน้าจะถูก
            # ต่อกันเป็นประโยคเดียว (เคยเกิด: "…ย้อนหลังได้ ระบบผ่านชุดทดสอบ…")
            for chunk in _PARA_SPLIT.split(block[1]):
                chunk = chunk.strip()
                if chunk:
                    out.append(Paragraph(esc(chunk), s['body']))
                    out.append(Spacer(1, 4))
        elif kind == 'note':
            out.append(Paragraph(esc(block[1]), s['note']))
            out.append(Spacer(1, 6))
        elif kind == 'bullets':
            for item in block[1]:
                text, detail = (item if isinstance(item, tuple)
                                else (item, ''))
                out.append(Paragraph(
                    f'<bullet>&bull;</bullet>{esc(text)}{esc(detail)}',
                    s['bullet']))
            out.append(Spacer(1, 6))
        elif kind == 'table':
            out.append(_data_table(block[1], s))
            out.append(Spacer(1, 12))
        elif kind == 'focus':
            rows = [[Paragraph(esc(a), s['td']), Paragraph(esc(b), s['td'])]
                    for a, b in block[1]]
            table = Table(rows, colWidths=[CONTENT_W * 0.36,
                                           CONTENT_W * 0.64])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6dae1')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef4fc')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            out.append(table)
            out.append(Spacer(1, 12))
    return out


# ---------------------------------------------------------------------------
# เอกสาร
# ---------------------------------------------------------------------------
def _page_furniture(canvas, chapter_title: list[str]):
    """เส้นบนหัวกระดาษ + เลขหน้าล่างกระดาษ

    Args:
        canvas: ได้จาก callback ของ PageTemplate (`BaseDocTemplate` ไม่มี
            แอตทริบิวต์ `.canvas` ใน reportlab 5.x — เรียกแล้วได้ AttributeError)
        chapter_title: รายการที่มีชื่อบทปัจจุบันเพียงค่าเดียว (เปลี่ยนทีละบท
            ผ่าน `_ChapterMarker`)
    """
    canvas.saveState()
    canvas.setFont(FONT_REGULAR, 8)
    canvas.setFillColor(diagrams.MUTED)
    canvas.drawString(MARGIN, PAGE_H - MARGIN + 8, 'THAMMATHAD SHOP — รายงานโครงการ')
    if chapter_title and chapter_title[0]:
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 8,
                               chapter_title[0][:70])
    canvas.setStrokeColor(colors.HexColor('#e6e9ef'))
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - MARGIN + 4, PAGE_W - MARGIN,
                PAGE_H - MARGIN + 4)
    canvas.line(MARGIN, MARGIN - 8, PAGE_W - MARGIN, MARGIN - 8)
    canvas.drawCentredString(PAGE_W / 2, MARGIN - 20, str(canvas.getPageNumber()))
    canvas.restoreState()


class _ChapterMarker(Flowable):
    """วัตถุไร้รูปที่แค่บอกว่า "ถึงบทนี้แล้ว" ตอนถูกเรนเดอร์

    จำเป็นเพราะ `build_pdf` ประกอบ story ทั้งเล่มให้เสร็จก่อนค่อยเรียก
    `doc.build()` ถ้าใช้รายการธรรมดาเก็บชื่อบท ตอนเรนเดอร์หน้าที่ 1
    รายการนั้นจะมีชื่อบท**ทั้งเล่ม**อยู่แล้ว ทำให้หัวกระดาษทุกหน้าขึ้นชื่อบทสุดท้าย
    """

    def __init__(self, title: str, sink: list[str]):
        super().__init__()
        self.title = title
        self.sink = sink
        self.width = 0
        self.height = 0

    def wrap(self, avail_width, avail_height):
        return 0, 0

    def draw(self):
        self.sink.append(self.title)
        self.sink[:] = [self.title]


def build_pdf(target: str, meta: dict, chapters: list[dict], diagrams_pack: dict,
             appendix_blocks: list[dict]) -> str:
    """ประกอบเอกสาร PDF ทั้งเล่มแล้วบันทึกลง `target`

    Args:
        target: พาธไฟล์ .pdf ปลายทาง
        meta: ข้อมูลปก (ดู `build_report`)
        chapters: รายการบทจาก `content.chapter_order()` เติม `title` แล้ว
        diagrams_pack: {key: (Drawing, คำบรรยาย)}
        appendix_blocks: บล็อกเนื้อหาภาคผนวก

    Returns:
        พาธไฟล์ที่บันทึกจริง
    """
    diagrams.register_thai_fonts()
    styles = _styles()

    doc = BaseDocTemplate(
        target, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=meta.get('title', ''), author=meta.get('student', {}).get(
            'ชื่อ-นามสกุล', ''))
    frame = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN, id='main')
    current: list[str] = ['']

    def on_page(canvas, _doc):
        _page_furniture(canvas, current)

    doc.addPageTemplates([PageTemplate(id='main', frames=[frame],
                                       onPage=on_page)])

    story: list = _cover(meta)

    # สารบัญ — เลขหน้าประมาณจากลำดับบท (ผู้เรียนต้องเติมเลขจริงตอนจัดพิมพ์)
    toc_rows = [('1', 1, 'บทที่ 1 บทนำ')]
    page_est = 2
    for i, ch in enumerate(chapters, start=1):
        page_est += 1
        toc_rows.append((str(i), page_est, ch['title']))
        page_est += max(1, len(ch['blocks']) // 6)
    toc_rows.append(('ภาค', page_est + 1, 'ภาคผนวก ก  ฐานข้อมูลและไดอะแกรม'))
    story += _toc(toc_rows)

    for chapter in chapters:
        story.append(_ChapterMarker(chapter['title'], current))
        story.append(Paragraph(esc(chapter['title']), styles['h1']))
        story += _block_renderer(chapter['blocks'], styles)
        story.append(PageBreak())

    if appendix_blocks:
        story.append(_ChapterMarker('ภาคผนวก', current))
        story.append(Paragraph('ภาคผนวก ก — ฐานข้อมูลและไดอะแกรม', styles['h1']))
        story += _block_renderer(appendix_blocks, styles)

        for key in ('er', 'layered', 'lifecycle', 'usecase'):
            item = diagrams_pack.get(key)
            if not item:
                continue
            drawing, caption = item
            story += _figure(drawing, caption, styles)
            if key == 'er':
                story.append(PageBreak())

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    doc.build(story)
    return target
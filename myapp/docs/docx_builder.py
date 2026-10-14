"""สร้างเอกสารรายงานเป็น Word (.docx) ด้วย python-docx

เหตุผลที่ต้องทำทั้ง PDF และ Word
    - PDF: อาจารย์เปิดดูได้ทันที ไม่ต้องมีโปรแกรมอะไร พิมพ์ได้เลย
    - Word: ผู้เรียนต้อง**แก้เองได้** (ใส่ชื่อ หน่ายรายงาน เพิ่มภาพหน้าจอ)

เนื้อหามาจาก `content.py` ชุดเดียวกับ PDF จึงไม่มีทางหลุดจากกัน

ข้อควรรู้
    python-docx ไม่รองรับการฝังกราฟเวกเตอร์ จึงต้องแปลงไดอะแกรมเป็น PNG
    ก่อนฝัง (ดู `render_diagram_png`) — ภาพจึงจะไม่คมเท่าใน PDF เมื่อขยาย
    ซึ่งเป็นข้อแลกเปลี่ยนที่หลีกเลี่ยงไม่ได้ ไม่ใช่ข้อผิดพลาด
"""

from __future__ import annotations

import io
import os
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import diagrams
from .diagrams import FONT_BOLD, FONT_REGULAR


#: ขนาดกระดาษ A4 เว้นขอบ 2.2 ซม. (ตรงกับ PDF)
PAGE_W_CM = 21.0
MARGIN_CM = 2.2
CONTENT_CM = PAGE_W_CM - 2 * MARGIN_CM


def render_diagram_png(drawing, dpi: int = 200) -> bytes:
    """แปลง Drawing เป็น PNG ในหน่วยความจำ

    ใช้ dpi สูง (200) เพราะ Word จะย่อภาพให้พอดีหน้ากระดาษเสมอ
    dpi ต่ำกว่านี้เมื่อขยายดูจะเห็นรอยหยาบขอบเส้น
    """
    from reportlab.graphics import renderPM

    buf = io.BytesIO()
    renderPM.drawToFile(drawing, buf, fmt='PNG', dpi=dpi)
    return buf.getvalue()


def _set_cell_background(cell, hex_color: str) -> None:
    """ใส่สีพื้นหลังเซลล์ (python-docx ไม่มี API ตรง ๆ ต้องเขียน XML)"""
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _style_run(run, size: float, bold: bool, color: tuple[int, int, int] | None,
               font: str | None = None) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    # ต้องตั้งทั้งชื่อฟอนต์สำหรับอักษรละตินและภาษาไทย (w:eastAsia)
    # ถ้าตั้งแค่ run.font.name Word จะใช้ฟอนต์ไทยของระบบแทน ทำให้
    # ข้อความในไฟล์ที่ส่งอาจารย์หน้าตาไม่เหมือนฉบับ PDF
    name = font or (FONT_BOLD if bold else FONT_REGULAR)
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(attr), name)


def _para(doc, text: str, size: float = 11, bold: bool = False,
          align=WD_ALIGN_PARAGRAPH.LEFT, space_after: float = 6,
          color: tuple[int, int, int] | None = None,
          justify: bool = False):
    """เพิ่มย่อหน้าหนึ่งย่อหน้า

    `justify` ถูกละเลยโดยตั้งใจ: การจัดข้อความไทยให้เต็มความกว้างสองข้าง
    จะยืดช่องว่างที่มี (ภาษาไทยไม่มีช่องว่างระหว่างคำ) ทำให้อ่านยาก
    ต้องตรงกับฝั่ง PDF ซึ่งใช้การจัดซ้ายเช่นกัน
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if justify else align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
    _style_run(p.add_run(text), size, bold, color)
    return p


def _table(doc, spec: dict, widths_cm: list[float] | None = None):
    head, rows = spec['head'], spec['rows']
    t = doc.add_table(rows=1, cols=len(head))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, h in enumerate(head):
        cell = t.rows[0].cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(str(h))
        _style_run(run, 9.5, True, (255, 255, 255))
        _set_cell_background(cell, '2B6CB0')

    for r_i, row in enumerate(rows):
        cells = t.add_row().cells
        for c_i, value in enumerate(row):
            cells[c_i].text = ''
            run = cells[c_i].paragraphs[0].add_run(str(value))
            _style_run(run, 9, False, (20, 24, 31))
            if r_i % 2 == 1:
                _set_cell_background(cells[c_i], 'F6F8FB')

    if widths_cm:
        for row in t.rows:
            for i, w in enumerate(widths_cm):
                if i < len(row.cells):
                    row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return t


def _picture(doc, png: bytes, caption: str, width_cm: float | None = None):
    width = width_cm or min(CONTENT_CM, 16.5)
    doc.add_picture(io.BytesIO(png), width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _para(doc, caption, 8.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14,
          color=(107, 114, 128))


def _page_break(doc):
    doc.add_page_break()


def _header_footer(section, chapter: str = '') -> None:
    header = section.header.paragraphs[0]
    header.text = ''
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _style_run(header.add_run(f'THAMMATHAD SHOP — รายงานโครงการ'
                              + (f'  |  {chapter}' if chapter else '')),
               8, False, (107, 114, 128))

    footer = section.footer.paragraphs[0]
    footer.text = ''
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _style_run(footer.add_run('หน้า '), 8, False, (107, 114, 128))
    # เลขหน้าแบบฟิลด์ (ไม่ใช่ตัวเลขตาย) — เพราะ Word จัดหน้าใหม่เอง
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    footer._p.append(fld)


def _cover(doc, meta: dict) -> None:
    for _ in range(3):
        doc.add_paragraph()

    _para(doc, 'รายงานโครงการวิชาปฏิบัติการ', 14, align=WD_ALIGN_PARAGRAPH.CENTER,
          space_after=18, color=(61, 69, 82))
    _para(doc, meta.get('title', ''), 24, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
    _para(doc, 'ระบบร้านค้าออนไลน์อุปกรณ์คอมพิวเตอร์และไอที', 14,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8,
          color=(61, 69, 82))
    _para(doc, 'THAMMATHAD SHOP', 12, align=WD_ALIGN_PARAGRAPH.CENTER,
          space_after=30, color=(107, 114, 128))

    doc.add_paragraph()
    for label, value in meta['student'].items():
        _para(doc, f'{label}: {value or "________________________________"}',
              12, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    doc.add_paragraph()
    _para(doc, meta.get('advisor', '') or
          'อาจารย์ที่ปรึกษา: ____________________',
          12, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    _para(doc, meta.get('year', ''), 12, align=WD_ALIGN_PARAGRAPH.CENTER,
          space_after=6)
    _page_break(doc)


def _toc(doc, entries: list[tuple[str, int, str]]) -> None:
    _para(doc, 'สารบัญ', 18, bold=True, space_after=14)
    _para(doc, '(เลขหน้าเป็นค่าประมาณ — ให้จัดหน้าอัตโนมัติที่ Word '
               'หรือเติมเองหลังจัดพิมพ์จริง)', 8.5, space_after=12,
          color=(107, 114, 128))
    for num, page, title in entries:
        _para(doc, f'{num}    {title}    {page}', 11, space_after=5)
    _page_break(doc)


def _render_blocks(doc, blocks: list) -> None:
    for block in blocks:
        kind = block[0]
        if kind == 'h2':
            _para(doc, block[1], 14, bold=True, space_after=8,
                  color=(43, 108, 176))
        elif kind == 'h3':
            _para(doc, block[1], 12.5, bold=True, space_after=6)
        elif kind == 'p':
            # แยกย่อหน้าตามบรรทัดว่างที่คนเขียนไว้ (ต้องตรงกับฝั่ง PDF)
            chunks = [c.strip() for c in re.split(r'\n[ \t]*\n', block[1])
                      if c.strip()]
            for chunk in chunks:
                _para(doc, chunk, 11, space_after=7)
        elif kind == 'note':
            _para(doc, block[1], 9.5, space_after=6, color=(154, 98, 8))
        elif kind == 'bullets':
            for item in block[1]:
                text, detail = (item if isinstance(item, tuple) else (item, ''))
                p = doc.add_paragraph(style='List Bullet')
                p.paragraph_format.space_after = Pt(4)
                p.paragraph_format.line_spacing = 1.3
                _style_run(p.add_run(text + detail), 11, False, (20, 24, 31))
            doc.add_paragraph()
        elif kind == 'table':
            _table(doc, block[1])
        elif kind == 'focus':
            _table(doc, {'head': ('สิ่งที่ตรวจ', 'รายละเอียดการทดสอบ'),
                         'rows': [list(r) for r in block[1]]},
                   widths_cm=[CONTENT_CM * 0.36, CONTENT_CM * 0.64])


def build_docx(target: str, meta: dict, chapters: list[dict],
               diagrams_pack: dict, appendix_blocks: list[dict]) -> str:
    """ประกอบเอกสาร Word ทั้งเล่มแล้วบันทึกลง `target`

    คืนค่า: พาธไฟล์ที่บันทึกจริง
    """
    diagrams.register_thai_fonts()
    doc = Document()

    section = doc.sections[0]
    section.page_width = Cm(PAGE_W_CM)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(MARGIN_CM)
    section.right_margin = Cm(MARGIN_CM)
    section.top_margin = Cm(MARGIN_CM)
    section.bottom_margin = Cm(MARGIN_CM)
    _header_footer(section)

    # สไตล์ปกติของเอกสาร ใช้เป็นค่าเริ่มต้นให้ข้อความใหม่
    normal = doc.styles['Normal']
    normal.font.name = FONT_REGULAR
    normal.font.size = Pt(11)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(attr), FONT_REGULAR)

    _cover(doc, meta)

    toc_rows = [('1', 1, 'บทที่ 1 บทนำ')]
    page_est = 2
    for i, ch in enumerate(chapters, start=1):
        page_est += 1
        toc_rows.append((str(i), page_est, ch['title']))
        page_est += max(1, len(ch['blocks']) // 6)
    toc_rows.append(('ภาค', page_est + 1, 'ภาคผนวก ก ฐานข้อมูลและไดอะแกรม'))
    _toc(doc, toc_rows)

    for chapter in chapters:
        _para(doc, chapter['title'], 18, bold=True, space_after=14)
        _render_blocks(doc, chapter['blocks'])
        _page_break(doc)

    if appendix_blocks:
        _para(doc, 'ภาคผนวก ก — ฐานข้อมูลและไดอะแกรม', 18, bold=True,
              space_after=14)
        _render_blocks(doc, appendix_blocks)
        for key in ('er', 'layered', 'lifecycle', 'usecase'):
            item = diagrams_pack.get(key)
            if not item:
                continue
            drawing, caption = item
            _picture(doc, render_diagram_png(drawing), caption)
            if key == 'er':
                _page_break(doc)

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    doc.save(target)
    return target
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
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import diagrams
from .content import TOTAL_TESTS
from .diagrams import FONT_BOLD, FONT_REGULAR


#: ขนาดกระดาษ A4 เว้นขอบ 2.2 ซม. (ตรงกับ PDF)
PAGE_W_CM = 21.0
MARGIN_CM = 2.2
CONTENT_CM = PAGE_W_CM - 2 * MARGIN_CM


def _split_appendix_title(title: str) -> tuple[str, str, str]:
    """แยกชื่อหัวข้อภาคผนวกเป็น (ส่วนหัวภาคผนวก, ชื่อภาษาไทย, ชื่อภาษาอังกฤษ) เพื่อจัดวางตามหลักวิชาการ"""
    m = re.match(r'^(ภาคผนวก\s+[ก-ฮA-Z])\s+(.+?)(?:\s*\((.+?)\))?$', title.strip())
    if m:
        app_label = m.group(1)
        th_title = m.group(2)
        en_title = f'({m.group(3)})' if m.group(3) else ''
        return app_label, th_title, en_title
    return title.strip(), '', ''


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
    # ใน Word ต้องตั้งชื่อฟอนต์ภาษาไทยเป็น TH Sarabun New และกำหนด w:eastAsia
    name = font or 'TH Sarabun New'
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(attr), name)


def _para(doc, text: str, size: float = 16, bold: bool = False,
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
    if spec.get('title'):
        _para(doc, spec['title'], 15, bold=True, space_after=4, color=(0, 0, 0))

    head, rows = spec['head'], spec['rows']
    t = doc.add_table(rows=1, cols=len(head))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    if widths_cm is None:
        n_cols = len(head)
        if n_cols == 2:
            widths_cm = [CONTENT_CM * 0.35, CONTENT_CM * 0.65]
        elif n_cols == 3:
            h0 = str(head[0])
            if 'บทบาท' in h0:
                widths_cm = [CONTENT_CM * 0.25, CONTENT_CM * 0.38, CONTENT_CM * 0.37]
            elif 'ด้าน' in h0:
                widths_cm = [CONTENT_CM * 0.24, CONTENT_CM * 0.40, CONTENT_CM * 0.36]
            else:
                widths_cm = [CONTENT_CM * 0.25, CONTENT_CM * 0.40, CONTENT_CM * 0.35]
        elif n_cols == 4:
            widths_cm = [CONTENT_CM * 0.16, CONTENT_CM * 0.26, CONTENT_CM * 0.28, CONTENT_CM * 0.30]
        elif n_cols == 6:
            widths_cm = [2.2, 3.2, 2.4, 2.4, 2.6, max(2.0, CONTENT_CM - (2.2 + 3.2 + 2.4 + 2.4 + 2.6))]

    for i, h in enumerate(head):
        cell = t.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        p.paragraph_format.line_spacing = 1.25
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(2)
        run = p.add_run(str(h))
        _style_run(run, 13.5, True, (0, 0, 0))
        _set_cell_background(cell, 'F0F0F0')

    for r_i, row in enumerate(rows):
        cells = t.add_row().cells
        for c_i, value in enumerate(row):
            cells[c_i].text = ''
            p = cells[c_i].paragraphs[0]
            p.paragraph_format.line_spacing = 1.25
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.space_before = Pt(2)
            run = p.add_run(str(value))
            _style_run(run, 13, False, (0, 0, 0))
            if r_i % 2 == 1:
                _set_cell_background(cells[c_i], 'FAFAFA')

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
    _para(doc, caption, 14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14,
          color=(0, 0, 0))


def _page_break(doc):
    doc.add_page_break()


def _header_footer(section, chapter: str = '') -> None:
    section.different_first_page_header_footer = True
    header = section.header.paragraphs[0]
    header.text = ''
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    # เลขหน้ามุมบนขวา
    run = header.add_run()
    _style_run(run, 14, False, (0, 0, 0))
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    run._r.append(fld)

    footer = section.footer.paragraphs[0]
    footer.text = ''


def _cover(doc, meta: dict) -> None:
    for _ in range(2):
        doc.add_paragraph()

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

    # ส่วนบน: ชื่อโครงงาน
    _para(doc, title_th, 20, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4, color=(0, 0, 0))
    _para(doc, '(THAMMATHAD SHOP)', 16, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4, color=(0, 0, 0))
    _para(doc, title_en.upper(), 14, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=36, color=(0, 0, 0))

    # ส่วนกลาง: ผู้จัดทำ และ เสนอ
    _para(doc, 'ผู้จัดทำ', 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3, color=(0, 0, 0))
    _para(doc, name or '________________________________', 16,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2, color=(0, 0, 0))
    _para(doc, f'รหัสนักศึกษา {std_id}' if std_id else 'รหัสนักศึกษา ____________________', 16,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18, color=(0, 0, 0))

    _para(doc, 'เสนอ', 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3, color=(0, 0, 0))
    _para(doc, advisor or 'ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย',
          16, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=36, color=(0, 0, 0))

    # ส่วนล่าง: สถาบัน
    _para(doc, f'รายงานนี้เป็นส่วนหนึ่งของรายวิชา {course}', 15,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3, color=(0, 0, 0))
    _para(doc, f'สาขาวิชา{dept} {faculty}', 15,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3, color=(0, 0, 0))
    _para(doc, univ, 16, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3, color=(0, 0, 0))
    _para(doc, f'ปีการศึกษา {year}', 15,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6, color=(0, 0, 0))
    _page_break(doc)


def _preface(doc, meta: dict) -> None:
    """หน้าคำนำในเอกสาร Word ตามหลักวิชาการ"""
    student = meta.get('student', {})
    name = student.get('ชื่อ-นามสกุล', 'นายธรรมธัช รูปไธสง')

    _para(doc, 'คำนำ', 18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14, color=(0, 0, 0))

    p1 = (
        'รายงานฉบับนี้จัดทำขึ้นเพื่อเป็นส่วนหนึ่งของรายวิชา 4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์ '
        '(Special Topics in Computer Science) หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาวิทยาการคอมพิวเตอร์ '
        'คณะวิทยาศาสตร์และเทคโนโลยี มหาวิทยาลัยราชภัฏกำแพงเพชร โดยมีวัตถุประสงค์เพื่อนำเสนอผลการศึกษา ค้นคว้า '
        'การวิเคราะห์ ออกแบบ และพัฒนาระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์และไอที (THAMMATHAD SHOP)'
    )
    p2 = (
        'เนื้อหาภายในเล่มประกอบด้วยการวิเคราะห์ความต้องการและกลุ่มผู้ใช้งานระบบ, การออกแบบสถาปัตยกรรมระบบ 4 ชั้น '
        '(4-Layer Clean Architecture) และแบบจำลองข้อมูลเชิงสัมพันธ์ (ERD), การพัฒนาโปรแกรมประยุกต์เว็บด้วยภาษา Python '
        'บนเฟรมเวิร์ก Django 6.0, การออกแบบส่วนต่อประสานผู้ใช้ตามแนวคิด Apple Liquid Glass Design, '
        'การพัฒนาระบบการเงินและจุดรับเงินจุดเดียว (Single Point of Payment Entry) ร่วมกับระบบตรวจสอบสลิปโอนเงินอัตโนมัติด้วย AI, '
        'ตลอดจนกระบวนการทดสอบระบบแบบอัตโนมัติ (Automated Testing) ครอบคลุม 412 กรณีทดสอบ'
    )
    p3 = (
        'ผู้จัดทำหวังเป็นอย่างยิ่งว่า รายงานฉบับนี้จะเป็นประโยชน์และเป็นแนวทางในการศึกษา ค้นคว้า '
        'ตลอดจนการประยุกต์ใช้ในการพัฒนาระบบเว็บแอปพลิเคชันพาณิชย์อิเล็กทรอนิกส์สำหรับผู้ที่สนใจ '
        'หากรายงานฉบับนี้มีข้อบกพร่องประการใด ผู้จัดทำขอน้อมรับข้อชี้แนะเพื่อนำไปปรับปรุงและพัฒนาต่อไป'
    )

    for p_text in (p1, p2, p3):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0)
        p.paragraph_format.first_line_indent = Cm(1.25)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.35
        _style_run(p.add_run(p_text), 16, False, (0, 0, 0))

    for _ in range(2):
        doc.add_paragraph()

    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sig.paragraph_format.right_indent = Cm(2.0)
    p_sig.paragraph_format.space_after = Pt(2)
    _style_run(p_sig.add_run(name), 16, True, (0, 0, 0))

    p_role = doc.add_paragraph()
    p_role.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_role.paragraph_format.right_indent = Cm(2.0)
    p_role.paragraph_format.space_after = Pt(6)
    _style_run(p_role.add_run('ผู้จัดทำโครงงาน'), 15, False, (0, 0, 0))

    _page_break(doc)


def _toc(doc, entries: list) -> None:
    """สารบัญ (Table of Contents) ในเอกสาร Word ตามหลักวิชาการ"""
    _para(doc, 'สารบัญ', 18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14, color=(0, 0, 0))

    t = doc.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    # กำหนดเส้นขอบตามหลักวิชาการ: บน 1.5pt, ล่าง 1.5pt, ไม่มีเส้นแนวตั้ง/แนวนอนภายใน
    tblBorders = OxmlElement('w:tblBorders')
    for b_name in ['left', 'right', 'insideH', 'insideV']:
        b = OxmlElement(f'w:{b_name}')
        b.set(qn('w:val'), 'none')
        tblBorders.append(b)

    top_b = OxmlElement('w:top')
    top_b.set(qn('w:val'), 'single')
    top_b.set(qn('w:sz'), '12')  # 1.5 pt
    top_b.set(qn('w:space'), '0')
    top_b.set(qn('w:color'), '000000')
    tblBorders.append(top_b)

    bot_b = OxmlElement('w:bottom')
    bot_b.set(qn('w:val'), 'single')
    bot_b.set(qn('w:sz'), '12')  # 1.5 pt
    bot_b.set(qn('w:space'), '0')
    bot_b.set(qn('w:color'), '000000')
    tblBorders.append(bot_b)
    t._tbl.tblPr.append(tblBorders)

    # แถวหัวตาราง
    hdr_cells = t.rows[0].cells
    hdr_cells[0].width = Cm(14.0)
    hdr_cells[1].width = Cm(1.5)

    p0 = hdr_cells[0].paragraphs[0]
    p0.paragraph_format.space_before = Pt(2)
    p0.paragraph_format.space_after = Pt(2)
    r0 = p0.add_run('บทที่')
    _style_run(r0, 15, True, (0, 0, 0))

    p1 = hdr_cells[1].paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p1.paragraph_format.space_before = Pt(2)
    p1.paragraph_format.space_after = Pt(2)
    r1 = p1.add_run('หน้า')
    _style_run(r1, 15, True, (0, 0, 0))

    # เส้นใต้แถวหัวตาราง 0.75 pt
    for c in hdr_cells:
        tcPr = c._tc.get_or_add_tcPr()
        tcBorders = OxmlElement('w:tcBorders')
        b = OxmlElement('w:bottom')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '6')  # 0.75 pt
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), '000000')
        tcBorders.append(b)
        tcPr.append(tcBorders)

    for entry in entries:
        # รองรับทั้ง (num, page, title) และ (num, title, page)
        if isinstance(entry[1], (int, str)) and str(entry[1]).isdigit():
            num, page, title = entry[0], str(entry[1]), str(entry[2])
        elif isinstance(entry[2], (int, str)) and (str(entry[2]).isdigit() or str(entry[2]) in ('ก', 'ข', 'ค', 'ง')):
            num, title, page = entry[0], str(entry[1]), str(entry[2])
        else:
            num, page, title = entry[0], str(entry[1]), str(entry[2])

        is_major = not num or num.startswith('บทที่') or title in (
            'สารบัญ', 'สารบัญเนื้อหา', 'สารบัญตาราง', 'สารบัญภาพ',
            'เอกสารอ้างอิงและบรรณานุกรม', 'ภาคผนวก'
        )

        row_cells = t.add_row().cells
        row_cells[0].width = Cm(14.0)
        row_cells[1].width = Cm(1.5)

        p_title = row_cells[0].paragraphs[0]
        p_title.paragraph_format.line_spacing = 1.25
        p_title.paragraph_format.space_before = Pt(1.5)
        p_title.paragraph_format.space_after = Pt(1.5)

        p_page = row_cells[1].paragraphs[0]
        p_page.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_page.paragraph_format.line_spacing = 1.25
        p_page.paragraph_format.space_before = Pt(1.5)
        p_page.paragraph_format.space_after = Pt(1.5)

        # Tab stop with dot leader for cell 0
        p_title.paragraph_format.tab_stops.add_tab_stop(
            Cm(13.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )

        if is_major and num.startswith('บทที่'):
            r_t = p_title.add_run(f'{num}    {title}\t')
            _style_run(r_t, 14, True, (0, 0, 0))
        elif is_major:
            r_t = p_title.add_run(f'{title}\t')
            _style_run(r_t, 14, True, (0, 0, 0))
        elif num.startswith('ภาคผนวก'):
            p_title.paragraph_format.left_indent = Cm(0.8)
            r_t = p_title.add_run(f'{num}  {title}\t')
            _style_run(r_t, 13.5, False, (0, 0, 0))
        else:
            p_title.paragraph_format.left_indent = Cm(0.8)
            r_t = p_title.add_run(f'{num}  {title}\t')
            _style_run(r_t, 13.5, False, (0, 0, 0))

        r_p = p_page.add_run(page)
        _style_run(r_p, 14 if is_major else 13.5, is_major, (0, 0, 0))

    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    _page_break(doc)


def _render_blocks(doc, blocks: list) -> None:
    for block in blocks:
        kind = block[0]
        if kind == 'h2':
            _para(doc, block[1], 16, bold=True, space_after=8,
                  color=(0, 0, 0))
        elif kind == 'h3':
            _para(doc, block[1], 16, bold=True, space_after=6, color=(0, 0, 0))
        elif kind == 'p':
            # แยกย่อหน้าตามบรรทัดว่างที่คนเขียนไว้ (ต้องตรงกับฝั่ง PDF)
            chunks = [c.strip() for c in re.split(r'\n[ \t]*\n', block[1])
                      if c.strip()]
            for chunk in chunks:
                p_elem = _para(doc, chunk, 16, space_after=7, color=(0, 0, 0))
                if not chunk.startswith('<b>'):
                    p_elem.paragraph_format.first_line_indent = Cm(1.25)
        elif kind == 'note':
            _para(doc, block[1], 14, space_after=6, color=(0, 0, 0))
        elif kind == 'bullets':
            for item in block[1]:
                text, detail = (item if isinstance(item, tuple) else (item, ''))
                clean_text = text.strip()
                if re.match(r'^\d+\.', clean_text):
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Cm(0.75)
                    p.paragraph_format.first_line_indent = Cm(-0.75)
                    p.paragraph_format.space_after = Pt(4)
                    p.paragraph_format.line_spacing = 1.35
                    _style_run(p.add_run(clean_text + ' '), 16, True, (0, 0, 0))
                    _style_run(p.add_run(detail.strip()), 16, False, (0, 0, 0))
                else:
                    p = doc.add_paragraph(style='List Bullet')
                    p.paragraph_format.space_after = Pt(4)
                    p.paragraph_format.line_spacing = 1.35
                    _style_run(p.add_run(text + detail), 16, False, (0, 0, 0))
            doc.add_paragraph()
        elif kind == 'page_break':
            _page_break(doc)
        elif kind == 'table':
            spec = block[1]
            title = spec.get('title', '')
            widths_cm = None
            if 'ก.1' in title or 'แหล่งเข้าถึงระบบ' in title:
                widths_cm = [4.4, 6.8, 4.3]
            elif 'ก.2' in title or 'บัญชีผู้ใช้' in title:
                widths_cm = [3.8, 2.0, 3.6, 6.1]
            elif 'ข.1' in title or 'สิทธิ์การเข้าถึง' in title:
                widths_cm = [4.0, 5.0, 6.5]
            elif 'ง.1' in title or 'ประวัติผู้จัดทำ' in title:
                widths_cm = [4.5, 11.0]
            _table(doc, spec, widths_cm=widths_cm)
        elif kind == 'focus':
            _para(doc, 'ตารางที่ 5.1 สาระสำคัญของการทดสอบระบบ (Test Focus)', 15, bold=True, space_after=4, color=(0, 0, 0))
            _table(doc, {'head': ('สิ่งที่ตรวจ', 'รายละเอียดการทดสอบ'),
                         'rows': [list(r) for r in block[1]]},
                    widths_cm=[CONTENT_CM * 0.36, CONTENT_CM * 0.64])
        elif kind == 'ref_item':
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.0)
            p.paragraph_format.first_line_indent = Cm(-1.0)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.35
            _style_run(p.add_run(block[1]), 15, False, (0, 0, 0))
        elif kind == 'image':
            img_path = block[1]
            caption = block[2] if len(block) > 2 else ''
            if os.path.exists(img_path):
                is_qr = 'qr' in img_path.lower() or 'qr' in caption.lower()
                w_cm = 4.0 if is_qr else 8.0
                with open(img_path, 'rb') as f:
                    _picture(doc, f.read(), caption, width_cm=w_cm)


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


def build_docx(target: str, meta: dict, chapters: list[dict],
               diagrams_pack: dict, appendix_blocks: list[dict],
               screenshots_pack: dict | None = None) -> str:
    """ประกอบเอกสาร Word ทั้งเล่มแล้วบันทึกลง `target`

    คืนค่า: พาธไฟล์ที่บันทึกจริง
    """
    diagrams.register_thai_fonts()
    if screenshots_pack is None:
        screenshots_pack = _default_screenshots_pack()
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
    normal.font.name = 'TH Sarabun New'
    normal.font.size = Pt(16)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(attr), 'TH Sarabun New')

    _cover(doc, meta)
    _preface(doc, meta)

    toc_rows = [
        ('', 'ก', 'คำนำ'),
        ('บทที่ 1', 1, 'บทนำ'),
        ('1.1', 1, 'ความเป็นมาและความสำคัญของโครงงาน'),
        ('1.2', 1, 'วัตถุประสงค์ของโครงงาน'),
        ('1.3', 2, 'ขอบเขตของระบบงาน'),
        ('1.4', 3, 'ประโยชน์ที่คาดว่าจะได้รับ'),
        ('บทที่ 2', 4, 'การวิเคราะห์และออกแบบระบบ'),
        ('2.1', 4, 'การวิเคราะห์ความต้องการของระบบ (Requirements Analysis)'),
        ('2.2', 5, 'การออกแบบกรณีการใช้งานและกลุ่มผู้ใช้ (Use Case & Actor Analysis)'),
        ('2.3', 6, 'การออกแบบสถาปัตยกรรมระบบ 4 ชั้น (4-Layer Clean Architecture)'),
        ('2.4', 7, 'การออกแบบแบบจำลองข้อมูลและความสัมพันธ์ (Data Modeling & ERD)'),
        ('2.5', 8, 'เมทริกซ์ความสัมพันธ์และกฎเกณฑ์ความคงสภาพ (Relationship Matrix)'),
        ('2.6', 9, 'การออกแบบเครื่องจักรสถานะคำสั่งซื้อ (Order Lifecycle State Machine)'),
        ('บทที่ 3', 10, 'การพัฒนาระบบ'),
        ('3.1', 10, 'สภาพแวดล้อมและเทคโนโลยีที่ใช้ในการพัฒนาระบบ (Technology Stack & Tools)'),
        ('3.2', 11, 'โครงสร้างโปรเจกต์และโมดูลระบบ (Project Directory Structure)'),
        ('3.3', 12, 'สถาปัตยกรรมส่วนต่อประสาน 2 โซน (Dual-Zone Architecture)'),
        ('3.4', 13, 'การพัฒนาระบบการเงินและจุดรับเงินจุดเดียว (Single Point of Payment Entry)'),
        ('3.5', 14, 'การพัฒนาระบบการแจ้งปัญหาและข้อร้องเรียนของลูกค้า (Order Issue Resolution)'),
        ('3.6', 15, 'ระบบบันทึกประวัติการทำงานแบบเพิ่มต่อท้าย (Append-Only Audit Trail)'),
        ('3.7', 16, 'การรักษาความมั่นคงปลอดภัยของระบบ (System Security & RBAC)'),
        ('บทที่ 4', 17, 'ผลการพัฒนาและภาพหน้าจอระบบ'),
        ('4.1', 17, 'ผลการพัฒนาส่วนต่อประสานสำหรับลูกค้า (Customer Storefront Zone)'),
        ('4.2', 20, 'ผลการพัฒนาส่วนต่อประสานสำหรับเจ้าหน้าที่ (Staff Management Zone)'),
        ('บทที่ 5', 23, 'การทดสอบและสรุปผล'),
        ('5.1', 23, 'ระเบียบวิธีและกลยุทธ์การทดสอบอัตโนมัติ'),
        ('5.2', 24, 'สาระสำคัญของการทดสอบระบบ'),
        ('5.3', 25, f'สรุปผลการรันชุดทดสอบอัตโนมัติ ({TOTAL_TESTS} Test Cases)'),
        ('5.4', 25, 'สรุปผลการดำเนินงานโครงงาน'),
        ('5.5', 26, 'ปัญหา อุปสรรค และแนวทางการแก้ไข'),
        ('5.6', 27, 'ข้อจำกัดและข้อเสนอแนะในการพัฒนาต่อยอด'),
        ('', 28, 'เอกสารอ้างอิงและบรรณานุกรม'),
        ('', 29, 'ภาคผนวก'),
        ('ภาคผนวก ก', 30, 'ข้อมูลการเข้าใช้งานระบบและแหล่งเก็บรหัสต้นฉบับ'),
        ('ภาคผนวก ข', 32, 'คู่มือการใช้งานระบบโดยย่อ'),
        ('ภาคผนวก ค', 34, 'พจนานุกรมข้อมูลและโครงสร้างระบบ'),
        ('ภาคผนวก ง', 44, 'ประวัติผู้จัดทำโครงงาน'),
    ]
    _toc(doc, toc_rows)

    for chapter in chapters:
        _para(doc, chapter['title'], 18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)
        for block in chapter['blocks']:
            _render_blocks(doc, [block])
            kind = block[0]
            if chapter['id'] == 'analysis' and kind == 'p':
                if 'ภาพที่ 2.1' in block[1] and 'usecase' in diagrams_pack:
                    d, cap = diagrams_pack['usecase']
                    _picture(doc, render_diagram_png(d), cap)
                elif 'ภาพที่ 2.2' in block[1] and 'layered' in diagrams_pack:
                    d, cap = diagrams_pack['layered']
                    _picture(doc, render_diagram_png(d), cap)
                elif 'ภาพที่ 2.3' in block[1] and 'er' in diagrams_pack:
                    d, cap = diagrams_pack['er']
                    _picture(doc, render_diagram_png(d), cap)
                elif 'ภาพที่ 2.4' in block[1] and 'lifecycle' in diagrams_pack:
                    d, cap = diagrams_pack['lifecycle']
                    _picture(doc, render_diagram_png(d), cap)

            if chapter['id'] == 'results' and kind == 'p':
                if '1. หน้าแรกและแคตตาล็อกสินค้า' in block[1]:
                    for fig_k in ('fig_4_1', 'fig_4_2', 'fig_4_3', 'fig_4_4', 'fig_4_5'):
                        if fig_k in screenshots_pack:
                            img_f, cap = screenshots_pack[fig_k]
                            if os.path.exists(img_f):
                                with open(img_f, 'rb') as f:
                                    _picture(doc, f.read(), cap, width_cm=15.0)
                elif '1. ตารางจัดการคำสั่งซื้อ' in block[1]:
                    for fig_k in ('fig_4_6', 'fig_4_7', 'fig_4_8', 'fig_4_9', 'fig_4_10'):
                        if fig_k in screenshots_pack:
                            img_f, cap = screenshots_pack[fig_k]
                            if os.path.exists(img_f):
                                with open(img_f, 'rb') as f:
                                    _picture(doc, f.read(), cap, width_cm=15.0)
        _page_break(doc)

    # เอกสารอ้างอิงและบรรณานุกรม
    from .content import REFERENCES
    if REFERENCES:
        _para(doc, 'เอกสารอ้างอิงและบรรณานุกรม', 18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)
        _render_blocks(doc, REFERENCES)
        _page_break(doc)

    if appendix_blocks:
        _page_break(doc)
        # หน้าบอกตอน "ภาคผนวก" ตามหลักวิชาการ
        for _ in range(8):
            doc.add_paragraph()
        _para(doc, 'ภาคผนวก', 24, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
        _para(doc, '(APPENDICES)', 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)
        _page_break(doc)

        first_app = True
        for block in appendix_blocks:
            kind = block[0]
            if kind == 'h2' and 'ภาคผนวก' in block[1]:
                if not first_app:
                    _page_break(doc)
                first_app = False
                app_label, th_title, en_title = _split_appendix_title(block[1])
                _para(doc, app_label, 18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3)
                if th_title:
                    _para(doc, th_title, 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3)
                if en_title:
                    _para(doc, en_title, 14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)
                continue
            if kind == 'page_break':
                _page_break(doc)
                continue
            _render_blocks(doc, [block])

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    doc.save(target)
    return target
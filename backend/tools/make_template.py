"""Build a master Word template.

    python tools/make_template.py                      -> templates/course_content.docx (generic)
    python tools/make_template.py --banner logo.png --out my_template.docx

In production the institution would author this file in Word and upload it.
This script exists so the sample template is reproducible and reviewable:
every font, colour, margin and table lives here, never in the renderer.
The {{ ... }} / {%p ... %} tags are Jinja, processed by docxtpl.
"""
import argparse
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1] / "templates"
RED, GREEN, BLUE = RGBColor(0xFF, 0x00, 0x00), RGBColor(0x70, 0xAD, 0x47), RGBColor(0x2F, 0x54, 0x96)
PEACH = "FBE4D5"
FONT = "Times New Roman"


def style(doc, name, *, size=11, bold=False, color=None, align=None, left=0.0, hanging=0.0,
          before=0, after=2, keep_next=False):
    s = doc.styles.add_style(name, 1)
    s.base_style = doc.styles["Normal"]
    f = s.font
    f.name, f.size, f.bold = FONT, Pt(size), bold
    s.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    if color is not None:
        f.color.rgb = color
    pf = s.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.left_indent = Cm(left + hanging)
    pf.first_line_indent = Cm(-hanging) if hanging else None
    pf.keep_with_next = keep_next
    if align is not None:
        pf.alignment = align
    if hanging:
        pf.tab_stops.add_tab_stop(Cm(left + hanging), WD_TAB_ALIGNMENT.LEFT)
    return s


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def put(cell, *runs, align=WD_ALIGN_PARAGRAPH.CENTER, style_name="AD Cell"):
    """runs: (text, bold, colour) tuples. Each Jinja tag sits whole inside one run."""
    p = cell.paragraphs[0]
    p.style = style_name
    p.alignment = align
    for text, bold, color in runs:
        r = p.add_run(text)
        r.bold = bold
        if color is not None:
            r.font.color.rgb = color
    return p


def field(paragraph, instr):
    for kind, text in (("begin", None), (None, instr), ("end", None)):
        r = paragraph.add_run()
        if kind:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); r._r.append(fc)
        else:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = text; r._r.append(it)


def tagpara(doc, tag, style_name="AD Body"):
    """A paragraph that holds only a {%p ... %} control tag (docxtpl removes it)."""
    return doc.add_paragraph(tag, style=style_name)


def main(banner: Path | None, out: Path, institution: list[str]):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(1.6), Cm(1.8)
    sec.header_distance = Cm(0.8)
    sec.different_first_page_header_footer = True

    n = doc.styles["Normal"]; n.font.name = FONT; n.font.size = Pt(11)
    J = WD_ALIGN_PARAGRAPH.JUSTIFY
    style(doc, "AD Title", size=12, bold=True, color=RED, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=6)
    ti = style(doc, "AD Title2", size=12, bold=True, color=RED, align=WD_ALIGN_PARAGRAPH.CENTER, before=2, after=2)
    ti.paragraph_format.page_break_before = False
    ol = OxmlElement("w:outlineLvl"); ol.set(qn("w:val"), "0")
    ti.element.get_or_add_pPr().append(ol)
    doc.styles["AD Title"].paragraph_format.page_break_before = True
    style(doc, "AD Section", size=12, bold=True, color=GREEN, before=8, after=3, keep_next=True)
    style(doc, "AD Lead", size=11, bold=True, left=0.4, after=3, keep_next=True)
    style(doc, "AD Body", align=J)
    style(doc, "AD Item", align=J, left=0.4, hanging=1.0)
    style(doc, "AD Outcome", align=J, left=0.9, hanging=1.3)
    style(doc, "AD Module", bold=True, before=6, after=2, keep_next=True)
    style(doc, "AD Part", align=J, after=3)
    style(doc, "AD Exercise", bold=True, color=BLUE, before=6, after=2, keep_next=True)
    style(doc, "AD ExItem", align=J, left=0.4, hanging=0.8, before=2, after=2, keep_next=True)
    style(doc, "AD ExSub", align=J, left=1.4, hanging=0.8, after=1)
    style(doc, "AD Cell", size=10, after=0)
    # character styles: the renderer picks one by name, the template decides what it looks like
    for nm, col in (("ADLabel", RED), ("ADStrong", None)):
        cs = doc.styles.add_style(nm, 2)
        cs.font.bold = True
        if col is not None:
            cs.font.color.rgb = col

    # --- first-page banner and page-number footer --------------------------------
    hp = sec.first_page_header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if banner:
        hp.add_run().add_picture(str(banner), width=Cm(15.6))
    else:   # text letterhead: name, status, address
        for i, line in enumerate(institution):
            p = hp if i == 0 else sec.first_page_header.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(line); r.bold = i < 2; r.font.name = FONT
            r.font.size = Pt(16 if i == 0 else 11); r.font.color.rgb = BLUE if i == 0 else None
    for ft in (sec.first_page_footer, sec.footer):
        p = ft.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(); r.bold = True
        field(p, "PAGE")
        p.add_run(" | Page").font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)

    # --- header table ----------------------------------------------------------
    doc.add_paragraph("COURSE CONTENT", style="AD Title")
    t = doc.add_table(rows=7, cols=9)
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    widths = [3.6, 3.6, 1.1, 1.1, 1.1, 1.5, 1.4, 1.4, 1.5]
    for row in t.rows:
        for c, w in zip(row.cells, widths):
            c.width = Cm(w)
    R = t.rows
    top = R[0].cells[0].merge(R[0].cells[8]); put(top, ("{{ course_title }}", True, RED), style_name="AD Title2")
    sem = R[1].cells[0].merge(R[1].cells[8])
    put(sem, ("{%p for o in offerings %}", False, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    p = sem.add_paragraph(style="AD Cell"); p.add_run("{{r o }}")
    sem.add_paragraph("{%p endfor %}", style="AD Cell")
    hdr = lambda cell, text: (put(cell, (text, True, None)), shade(cell, PEACH))
    hdr(R[2].cells[0], "Course Code"); hdr(R[2].cells[1], "Category")
    hdr(R[2].cells[2].merge(R[2].cells[4]), "Hours / Week")
    hdr(R[2].cells[5], "Credits"); hdr(R[2].cells[6].merge(R[2].cells[8]), "Maximum Marks")
    code = R[3].cells[0].merge(R[4].cells[0]); put(code, ("{{ course_code }}", True, None))
    cat = R[3].cells[1].merge(R[4].cells[1]); put(cat, ("{{ category }}", True, BLUE))
    for i, lab in zip(range(2, 9), ["L", "T", "P", "C", "CIA", "SEE", "Total"]):
        put(R[3].cells[i], (lab, True, None))
    for i, val in zip(range(2, 9), ["{{ L }}", "{{ T }}", "{{ P }}", "{{ C }}", "{{ cia }}", "{{ see }}", "{{ total }}"]):
        put(R[4].cells[i], (val, False, None))
    for cell, label, tag in [
        (R[5].cells[0], "Contact Classes: ", "{{ contact }}"),
        (R[5].cells[1], "Tutorial Classes: ", "{{ tutorial }}"),
        (R[5].cells[2].merge(R[5].cells[5]), "Practical Classes: ", "{{ practical }}"),
        (R[5].cells[6].merge(R[5].cells[8]), "Total Classes: ", "{{ total_classes }}"),
    ]:
        put(cell, (label, True, RED), (tag, True, None)); shade(cell, PEACH)
    pre = R[6].cells[0].merge(R[6].cells[8])
    put(pre, ("Prerequisite: ", True, RED), ("{{ prerequisite }}", True, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    shade(pre, PEACH)

    # --- body ------------------------------------------------------------------
    def section(title, tag=None):
        if tag:
            tagpara(doc, "{%p if " + tag + " %}")
        doc.add_paragraph(title, style="AD Section")

    section("I. COURSE OVERVIEW:")
    doc.add_paragraph("{{ overview }}", style="AD Body")

    section("II. COURSE OBJECTIVES:")
    doc.add_paragraph("The students will try to learn:", style="AD Lead")
    tagpara(doc, "{%p for o in objectives %}")
    doc.add_paragraph("{{ o.n }}\t{{ o.text }}", style="AD Item")
    tagpara(doc, "{%p endfor %}")

    section("III. COURSE OUTCOMES:")
    doc.add_paragraph("After successful completion of the course, students should be able to:", style="AD Lead")
    tagpara(doc, "{%p for o in outcomes %}")
    doc.add_paragraph("{{ o.n }}\t{{ o.text }}", style="AD Outcome")
    tagpara(doc, "{%p endfor %}")

    doc.add_paragraph("IV. COURSE CONTENT:", style="AD Section")
    # theory
    tagpara(doc, "{%p for m in modules %}")
    doc.add_paragraph("{{ m.heading }}", style="AD Module")
    tagpara(doc, "{%p for p in m.parts %}")
    doc.add_paragraph("{{r p.rt }}", style="AD Part")
    tagpara(doc, "{%p endfor %}")
    tagpara(doc, "{%p endfor %}")
    # laboratory
    tagpara(doc, "{%p for ex in exercises %}")
    doc.add_paragraph("{{ ex.heading }}", style="AD Exercise")
    tagpara(doc, "{%p for it in ex.entries %}")
    doc.add_paragraph("{{ it.n }}\t{{ it.text }}", style="AD ExItem")
    tagpara(doc, "{%p if it.table %}")
    tb = doc.add_table(rows=4, cols=2)
    tb.style = "Table Grid"; tb.alignment = WD_TABLE_ALIGNMENT.CENTER; tb.autofit = False
    for row in tb.rows:
        row.cells[0].width, row.cells[1].width = Cm(4.0), Cm(5.0)
    put(tb.rows[0].cells[0], ("{{ it.table.header[0] }}", True, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    put(tb.rows[0].cells[1], ("{{ it.table.header[1] }}", True, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    put(tb.rows[1].cells[0], ("{%tr for r in it.table.rows %}", False, None))
    put(tb.rows[2].cells[0], ("{{ r[0] }}", False, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    put(tb.rows[2].cells[1], ("{{ r[1] }}", False, None), align=WD_ALIGN_PARAGRAPH.LEFT)
    put(tb.rows[3].cells[0], ("{%tr endfor %}", False, None))
    doc.add_paragraph("", style="AD Cell")
    tagpara(doc, "{%p endif %}")
    tagpara(doc, "{%p for s in it.subs %}")
    doc.add_paragraph("{{ s.n }}\t{{ s.text }}", style="AD ExSub")
    tagpara(doc, "{%p endfor %}")
    tagpara(doc, "{%p endfor %}")
    tagpara(doc, "{%p endfor %}")

    def booklist(title, var, item="b"):
        section(title, var)
        tagpara(doc, "{%p for " + item + " in " + var + " %}")
        doc.add_paragraph("{{ " + item + ".n }}\t{{ " + item + ".text }}", style="AD Item")
        tagpara(doc, "{%p endfor %}")
        tagpara(doc, "{%p endif %}")

    booklist("V. TEXT BOOKS:", "text_books")
    booklist("VI. REFERENCE BOOKS:", "reference_books")
    booklist("VII. ELECTRONIC RESOURCES:", "electronic_resources")
    booklist("VIII. MATERIALS ONLINE:", "materials_online")

    # tidy: the first paragraph python-docx creates is empty
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print("wrote", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banner", type=Path, help="letterhead image for the first page")
    ap.add_argument("--out", type=Path, default=ROOT / "course_content.docx")
    ap.add_argument("--institution", nargs="+",
                    default=["EXAMPLE INSTITUTE OF TECHNOLOGY", "(Autonomous)", "Example City - 000 000"])
    a = ap.parse_args()
    main(a.banner, a.out, a.institution)

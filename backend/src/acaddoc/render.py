"""Course JSON -> DOCX through the institution's master template.

This module decides *what text appears* (numbering, 'Nil' for zero, upper-case
module titles). It never decides how the text looks: fonts, colours, indents
and tables all come from the template.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from docxtpl import DocxTemplate, RichText

from .schema import Course
from .validate import Issue, blocking, validate

# The institution's template. Set ACADDOC_TEMPLATE to use your own.
TEMPLATE = Path(os.environ.get("ACADDOC_TEMPLATE")
                or Path(__file__).resolve().parents[2] / "templates" / "course_content.docx")

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


class InvalidCourse(Exception):
    def __init__(self, course: Course, issues: list[Issue]):
        self.issues = issues
        super().__init__(f"{course.course_code}: {len(issues)} blocking issue(s)\n" + "\n".join(map(str, issues)))


def _dash(n: int) -> str:
    return str(n) if n else "-"


def _nil(n: int) -> str:
    return str(n) if n else "Nil"


def _numbered(items: list[str]) -> list[dict]:
    return [{"n": f"{i}.", "text": t} for i, t in enumerate(items, 1)]


def context(c: Course) -> dict:
    h = c.hours
    offerings = []
    for o in c.offerings:
        rt = RichText()
        rt.add(f"{o.semester} Semester: ", style="ADLabel")
        rt.add(" / ".join(o.programmes), style="ADStrong")
        offerings.append(rt)

    modules = []
    for i, m in enumerate(c.modules):
        parts = []
        for p in m.parts:
            rt = RichText()
            if p.label:
                rt.add(f"{p.label}: ", style="ADStrong")
            rt.add(p.text)
            parts.append({"rt": rt})
        hours = f" ({m.hours:02d})" if m.hours is not None else ""
        modules.append({"heading": f"MODULE – {_ROMAN[i]}: {m.title.upper()}{hours}", "parts": parts})

    exercises = []
    for i, ex in enumerate(c.exercises, 1):
        items = []
        for j, it in enumerate(ex.items, 1):
            items.append({
                "n": f"{j}.", "text": it.text,
                "table": ({"header": it.table.header, "rows": it.table.rows} if it.table else None),
                "subs": [{"n": f"{chr(96 + k)}.", "text": s} for k, s in enumerate(it.subitems, 1)],
            })
        exercises.append({"heading": f"EXERCISE – {i}: {ex.title.upper()}", "entries": items})

    return {
        "course_title": c.course_title.upper(), "course_code": c.course_code, "category": c.category,
        "offerings": offerings,
        "L": _dash(h.lecture), "T": _dash(h.tutorial), "P": _dash(h.practical), "C": h.credits,
        "cia": c.marks.cia, "see": c.marks.see, "total": c.marks.total,
        "contact": _nil(h.contact_classes), "tutorial": _nil(h.tutorial_classes),
        "practical": _nil(h.practical_classes), "total_classes": h.total_classes,
        "prerequisite": c.prerequisite or "Nil",
        "overview": c.overview,
        "objectives": [{"n": f"{_ROMAN[i]}.", "text": t} for i, t in enumerate(c.objectives)],
        "outcomes": [{"n": f"CO {i}", "text": o.text} for i, o in enumerate(c.outcomes, 1)],
        "modules": modules, "exercises": exercises,
        "text_books": _numbered(c.text_books),
        "reference_books": _numbered(c.reference_books),
        "electronic_resources": _numbered(c.electronic_resources),
        "materials_online": _numbered(c.materials_online),
    }


def render_docx(c: Course, out: Path, *, template: Path = TEMPLATE, allow_errors: bool = False) -> list[Issue]:
    """Validate, then render. Blocking issues stop generation unless allow_errors."""
    issues = validate(c)
    if blocking(issues) and not allow_errors:
        raise InvalidCourse(c, blocking(issues))
    tpl = DocxTemplate(str(template))
    tpl.render(context(c), autoescape=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out))
    return issues


def to_pdf(docx: Path, pdf: Path | None = None) -> Path:
    """DOCX -> PDF. LibreOffice if present (servers), otherwise Word (this PC)."""
    pdf = pdf or docx.with_suffix(".pdf")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf.parent), str(docx)],
                       check=True, capture_output=True)
        return pdf
    script = (
        "$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
        f"$d=$w.Documents.Open('{docx.resolve()}');foreach($t in $d.TablesOfContents){{$t.Update()}};"
        f"$d.ExportAsFixedFormat('{pdf.resolve()}',17);$d.Close($false);$w.Quit()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True)
    return pdf

"""Tests built around the actual problem: consistent, compliant documents.

Run:  python -m pytest -q      (from the acaddoc folder)
"""
from __future__ import annotations

import copy
import glob
import json
import shutil
from pathlib import Path

import pytest
from docx import Document

from acaddoc.handbook import build_handbook
from acaddoc.render import InvalidCourse, render_docx, to_pdf
from acaddoc.schema import Course
from acaddoc.validate import blocking, validate

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(glob.glob(str(ROOT / "samples" / "*.json")))


def load(code: str) -> dict:
    return json.loads((ROOT / "samples" / f"{code}.json").read_text(encoding="utf-8"))


def course(code="MTH101", **change) -> Course:
    d = load(code)
    d.update(change)
    return Course.model_validate(d)


def rules(c: Course) -> set[str]:
    return {i.rule for i in validate(c)}


# --- validation -----------------------------------------------------------------

def test_clean_course_has_no_issues():
    assert validate(course("MTH101")) == []


def test_three_modules_instead_of_five_is_blocked():
    d = load("MTH101"); d["modules"] = d["modules"][:3]
    assert "MODULE_COUNT" in rules(Course.model_validate(d))


def test_ten_outcomes_is_blocked():
    d = load("MTH101"); d["outcomes"] += [{"code": f"CO{i}", "text": "Extra outcome."} for i in range(7, 11)]
    assert "OUTCOME_COUNT" in rules(Course.model_validate(d))


def test_marks_must_add_up():
    d = load("MTH101"); d["marks"]["total"] = 99
    assert "MARKS_TOTAL" in rules(Course.model_validate(d))


def test_module_hours_must_match_contact_classes():
    d = load("MTH101"); d["modules"][0]["hours"] += 1
    assert "MODULE_HOURS_SUM" in rules(Course.model_validate(d))


def test_outcome_numbering_gap():
    d = load("MTH101"); d["outcomes"][2]["code"] = "CO4"
    assert "OUTCOME_NUMBERING" in rules(Course.model_validate(d))


def test_leftover_verb_is_flagged_but_make_use_of_is_not():
    d = load("MTH101")
    d["outcomes"][0]["text"] = "Compare Identify suitable methods."
    d["outcomes"][1]["text"] = "Make Use of the theorem."
    found = {i.where for i in validate(Course.model_validate(d)) if i.rule == "OUTCOME_TWO_VERBS"}
    assert found == {"outcomes[1]"}


@pytest.mark.parametrize("code,edit,rule", [
    ("MTH101", lambda d: d.update(overview="  "), "OVERVIEW_REQUIRED"),
    ("MTH101", lambda d: d["offerings"][0].update(programmes=[]), "OFFERING_PROGRAMMES"),
    ("MTH101", lambda d: d.update(offerings=[]), "OFFERING_REQUIRED"),
    ("MTH101", lambda d: d["modules"][2].update(title=""), "MODULE_TITLE_REQUIRED"),
    ("MTH101", lambda d: d["modules"][2].update(parts=[{"text": " "}]), "MODULE_EMPTY"),
    ("CSE206", lambda d: d["exercises"][1].update(title=""), "EXERCISE_TITLE_REQUIRED"),
    ("CSE206", lambda d: d["exercises"][3].update(items=[{"text": "", "subitems": []}]), "EXERCISE_EMPTY"),
])
def test_blank_required_content_is_an_error(code, edit, rule):
    d = load(code); edit(d)
    issues = [i for i in validate(Course.model_validate(d)) if i.rule == rule]
    assert issues and issues[0].severity == "error"


def test_unknown_field_is_rejected():
    d = load("MTH101"); d["coursetitle"] = "typo"
    with pytest.raises(Exception):
        Course.model_validate(d)


def test_all_samples_are_clean():
    for f in FILES:
        assert validate(Course.model_validate_json(Path(f).read_text(encoding="utf-8"))) == []


def broken(code="CSE205") -> Course:
    """A sample whose module hours no longer add up to its contact classes."""
    d = load(code); d["modules"][0]["hours"] += 1
    return Course.model_validate(d)


# --- rendering ------------------------------------------------------------------

def test_blocked_course_is_not_rendered(tmp_path):
    with pytest.raises(InvalidCourse):
        render_docx(broken(), tmp_path / "x.docx")
    assert not (tmp_path / "x.docx").exists()


def _text(path: Path) -> str:
    d = Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)


@pytest.mark.parametrize("path", FILES, ids=lambda p: Path(p).stem)
def test_every_sample_course_renders_with_all_its_content(path, tmp_path):
    c = Course.model_validate_json(Path(path).read_text(encoding="utf-8"))
    out = tmp_path / "c.docx"
    render_docx(c, out, allow_errors=True)
    text = _text(out)
    assert "{{" not in text and "{%" not in text           # no unreplaced tags
    assert c.course_code in text and c.course_title.upper() in text
    for o in c.outcomes:
        assert o.text.split()[0] in text
    for m in c.modules:
        assert m.title.upper() in text
        for p in m.parts:
            assert p.text in text
    for ex in c.exercises:
        assert ex.title.upper() in text
        for it in ex.items:
            for s in it.subitems:
                assert s in text
    for b in c.text_books + c.reference_books:
        assert b in text


def test_all_documents_use_exactly_the_same_styles(tmp_path):
    """100-courses-look-identical, in miniature: styles come only from the template."""
    template_styles = {s.name for s in Document(str(ROOT / "templates" / "course_content.docx")).styles}
    used_by = {}
    for f in FILES:
        c = Course.model_validate_json(Path(f).read_text(encoding="utf-8"))
        out = tmp_path / f"{c.course_code}.docx"
        render_docx(c, out, allow_errors=True)
        d = Document(str(out))
        used = {p.style.name for p in d.paragraphs}
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    used |= {p.style.name for p in cell.paragraphs}
        assert used <= template_styles
        used_by[c.course_code] = used
        # the renderer must not set fonts or sizes on any run
        for p in d.paragraphs:
            for r in p.runs:
                assert r.font.name is None and r.font.size is None
    theory = [v for k, v in used_by.items() if k != "CSE206"]
    assert all(v - {"Normal"} <= theory[0] | {"AD Cell"} for v in theory)


def test_long_unbreakable_text_does_not_break_rendering(tmp_path):
    d = load("CSE206")
    d["exercises"][1]["items"][0]["table"]["rows"][0][0] = "X" * 200
    d["exercises"][1]["items"][0]["text"] = "word " * 300
    out = tmp_path / "long.docx"
    render_docx(Course.model_validate(d), out)
    assert "X" * 200 in _text(out)


def test_ampersand_and_angle_brackets_survive(tmp_path):
    d = load("MTH101")
    d["modules"][0]["parts"][0]["text"] = "Salt & pepper <b>not bold</b> \"quoted\""
    d["offerings"][0]["programmes"][0] = "CSE (AI & ML)"
    out = tmp_path / "esc.docx"
    render_docx(Course.model_validate(d), out)
    t = _text(out)
    assert "Salt & pepper <b>not bold</b>" in t and "CSE (AI & ML)" in t


def test_large_reference_list_paginates(tmp_path):
    d = load("MTH101")
    d["reference_books"] = [f"Author {i}, Book {i}, Publisher, 20{i % 25:02d}." for i in range(60)]
    out = tmp_path / "refs.docx"
    render_docx(Course.model_validate(d), out)
    assert "60.\tAuthor 59" in "\n".join(p.text for p in Document(str(out)).paragraphs)
    if shutil.which("soffice") or shutil.which("libreoffice") or Path(r"C:\Program Files\Microsoft Office").exists():
        import pdfplumber
        with pdfplumber.open(to_pdf(out)) as pdf:
            pages = [pg.extract_text() or "" for pg in pdf.pages]
            first = next(i for i, t in enumerate(pages) if "Author 0," in t)
            last = next(i for i, t in enumerate(pages) if "Author 59," in t)
            assert last > first   # the list ran on to another page, nothing was cut


# --- handbook -------------------------------------------------------------------

def test_handbook_excludes_blocked_courses_and_orders_by_semester(tmp_path):
    courses = [Course.model_validate_json(Path(f).read_text(encoding="utf-8")) for f in FILES]
    courses = [broken() if c.course_code == "CSE205" else c for c in courses]
    res = build_handbook(courses, "CSE", "2026-27", tmp_path / "hb.docx")
    assert set(res.excluded) == {"CSE205"}
    assert [c.course_code for c in res.included] == ["MTH101", "ENG103", "CSE206"]
    text = _text(tmp_path / "hb.docx")
    assert "ENG103" in text and "DATA STRUCTURES LABORATORY" in text


def test_programme_with_semester_that_differs_per_programme():
    # ENG103 is I Semester for ECE and ME but II Semester for CSE.
    c = course("ENG103")
    from acaddoc.handbook import semester_of
    assert semester_of(c, "CSE") == "II"
    assert semester_of(c, "ECE") == "I"
    assert semester_of(c, "Mathematics") is None

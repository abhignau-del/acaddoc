"""Bloom levels, CO-PO mapping and programme outcomes."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from acaddoc.api import create_app
from acaddoc.handbook import build_handbook
from acaddoc.outcomes import (
    LOCF_OUTCOMES, columns, course_level, framework, mapping_programme, suggest_bloom,
)
from acaddoc.render import render_docx
from acaddoc.schema import Course, ProgrammeRecord
from acaddoc.store import Store
from acaddoc.validate import validate

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
PW = "correct horse"


def load(code: str) -> dict:
    return json.loads((SAMPLES / f"{code}.json").read_text(encoding="utf-8"))


def prog(code: str) -> ProgrammeRecord:
    return ProgrammeRecord.model_validate_json((SAMPLES / "programmes" / f"{code}.json").read_text(encoding="utf-8"))


def course(code="CSE205", edit=None) -> Course:
    d = load(code)
    if edit:
        edit(d)
    return Course.model_validate(d)


def rules(c: Course, fw=None) -> set[str]:
    return {i.rule for i in validate(c, fw)}


# --- Bloom ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text,level", [
    ("Determine the rank of a matrix", "apply"),
    ("Make use of SQL joins", "apply"),
    ("Evaluate the integral by parts", "apply"),          # an operation, not judgement
    ("Evaluate competing designs", "evaluate"),
    ("Students will be able to design a parser", "create"),
    ("Construct a model of population growth", "create"),
    ("Construct binary search trees", "apply"),
    ("Understand recursion", "understand"),
    ("Recursion is covered", None),
    ("", None),
])
def test_bloom_suggestion_reads_the_opening_verb(text, level):
    assert suggest_bloom(text) == level


def test_bloom_must_be_a_known_level():
    with pytest.raises(Exception):
        course(edit=lambda d: d["outcomes"][0].update(bloom="memorise"))


# --- schema and validation -----------------------------------------------------------------

def test_strength_is_one_to_three_and_codes_are_checked():
    for bad in ({"PO1": 0}, {"PO1": 4}, {"po1": 2}, {"PO-1": 2}):
        with pytest.raises(Exception):
            course(edit=lambda d, b=bad: d["outcomes"][0].update(po=b))


def test_courses_saved_before_v040_still_load():
    d = load("MTH101")
    for o in d["outcomes"]:
        o.pop("bloom"); o.pop("po")
    c = Course.model_validate(d)
    assert c.outcomes[0].po == {} and c.outcomes[0].bloom is None and c.po_programme == ""
    assert {"OUTCOME_BLOOM_MISSING", "COPO_EMPTY"} <= rules(c)
    assert all(i.severity == "warning" for i in validate(c) if i.rule in ("OUTCOME_BLOOM_MISSING", "COPO_EMPTY"))


def test_unmapped_outcomes_are_named():
    c = course(edit=lambda d: (d["outcomes"][1].update(po={}), d["outcomes"][4].update(po={})))
    issue = next(i for i in validate(c) if i.rule == "CO_UNMAPPED")
    assert "CO2, CO5" in issue.message and issue.severity == "warning"


def test_copo_required_turns_the_warning_into_an_error(monkeypatch):
    monkeypatch.setitem(__import__("acaddoc.validate", fromlist=["RULES"]).RULES, "copo_required", True)
    c = course(edit=lambda d: d["outcomes"][1].update(po={}))
    assert next(i for i in validate(c) if i.rule == "CO_UNMAPPED").severity == "error"


def test_unknown_programme_outcome_is_an_error_only_when_the_framework_is_known():
    c = course(edit=lambda d: d["outcomes"][0]["po"].update(PO12=2))
    assert "PO_UNKNOWN" not in rules(c)                                        # framework not given
    issues = [i for i in validate(c, prog("CSE").outcomes) if i.rule == "PO_UNKNOWN"]
    assert len(issues) == 1 and "PO12" in issues[0].message and issues[0].severity == "error"
    assert issues[0].where == "copo.CO1"


def test_samples_are_clean_against_their_programmes():
    for f in sorted(SAMPLES.glob("*.json")):
        c = Course.model_validate_json(f.read_text(encoding="utf-8"))
        code = mapping_programme(c)
        rec = prog(code) if (SAMPLES / "programmes" / f"{code}.json").exists() else None
        assert validate(c, framework(code, rec).outcomes) == [], c.course_code


# --- frameworks and arithmetic ---------------------------------------------------------------

def test_mapping_programme_defaults_to_the_first_offered():
    assert mapping_programme(course("ENG103")) == "ECE"                       # I Sem: ECE, ME; II Sem: CSE
    assert mapping_programme(course("ENG103", lambda d: d.update(po_programme="CSE"))) == "CSE"
    assert mapping_programme(course("MTH101", lambda d: d.update(offerings=[]))) == ""


def test_programme_without_outcomes_falls_back_to_locf():
    fw = framework("ME", None)
    assert fw.source == "locf" and fw.codes == [o.code for o in LOCF_OUTCOMES] and len(fw.codes) == 9
    assert framework("ME", ProgrammeRecord(code="ME", name="B.Tech. ME")).source == "locf"   # record, no outcomes
    assert framework("CSE", prog("CSE")).source == "programme"


def test_columns_keep_programme_order_then_extra_codes():
    c = course(edit=lambda d: d["outcomes"][0]["po"].update(PO12=1, PO10=1))
    assert columns(c, framework("CSE", prog("CSE")))[-4:] == ["PSO1", "PSO2", "PO10", "PO12"]
    assert columns(course(), None) == ["PO1", "PO2", "PO3", "PSO1", "PSO2"]


def test_course_level_is_the_rounded_mean_of_its_links():
    c = course()                                   # CSE205: PSO1 links 2,3,3,3,3,2 -> 2.67 -> 3; PO1 3,2 -> 2.5 -> 3
    assert course_level(c, "PSO1") == 3 and course_level(c, "PO1") == 3
    assert course_level(c, "PSO2") == 2 and course_level(c, "PO9") is None
    c = course(edit=lambda d: [o.update(po={"PO4": v}) for o, v in zip(d["outcomes"], [1, 2, 1, 2, 1, 2])])
    assert course_level(c, "PO4") == 2                                          # 1.5 rounds up, not to even


# --- documents ---------------------------------------------------------------------------------

def _tables(path: Path) -> list[list[list[str]]]:
    return [[[c.text for c in row.cells] for row in t.rows] for t in Document(str(path)).tables]


def _text(path: Path) -> str:
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_syllabus_prints_bloom_levels_and_the_copo_table(tmp_path):
    c = course()
    out = tmp_path / "c.docx"
    render_docx(c, out, framework=framework("CSE", prog("CSE")))
    text = _text(out)
    assert "Analyse the time and space complexity of simple algorithms. (Analyse)" in text
    assert "Programme outcomes of B.Tech. Computer Science and Engineering. 3 = High" in text
    copo = next(t for t in _tables(out) if t[0][0] == "CO")
    assert copo[0] == ["CO", "PO1", "PO2", "PO3", "PO4", "PO5", "PO6", "PO7", "PO8", "PO9", "PSO1", "PSO2"]
    assert copo[1] == ["CO 1", "3", "3", "-", "-", "-", "-", "-", "-", "-", "2", "-"]
    assert len(copo) == 7


def test_no_mapping_no_table(tmp_path):
    c = course(edit=lambda d: [o.update(po={}, bloom=None) for o in d["outcomes"]])
    out = tmp_path / "c.docx"
    render_docx(c, out, framework=framework("CSE", prog("CSE")))
    assert not any(t[0][0] == "CO" for t in _tables(out))
    assert "Mapping of course outcomes" not in _text(out) and "(Analyse)" not in _text(out)


def test_locf_note_says_the_programme_has_not_set_outcomes(tmp_path):
    c = course(edit=lambda d: [o.update(po={"GA1": 2}) for o in d["outcomes"]])
    out = tmp_path / "c.docx"
    render_docx(c, out, framework=framework("CSE", None))
    assert "UGC LOCF graduate attributes (CSE has not set its own programme outcomes)" in _text(out)


def test_handbook_lists_programme_outcomes_and_the_course_matrix(tmp_path):
    courses = [Course.model_validate_json(f.read_text(encoding="utf-8")) for f in sorted(SAMPLES.glob("*.json"))]
    recs = {"CSE": prog("CSE"), "ECE": prog("ECE")}
    out = tmp_path / "hb.docx"
    build_handbook(courses, "CSE", "2026-27", out, framework_for=lambda code: framework(code, recs.get(code)))
    text = _text(out)
    assert "PROGRAMME OUTCOMES" in text and "Software development: " in text
    matrix = next(t for t in _tables(out) if t[0][0] == "Course")
    assert [r[0] for r in matrix[1:]] == ["MTH101", "CSE205", "CSE206"]       # ENG103 is mapped to ECE
    assert "Not addressed by any course in this handbook: PO6, PO9." in text
    assert "ENG103 (ECE)" in text


# --- API -----------------------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    users = {
        "admin": store.create_user("admin", "Admin", PW, "admin"),
        "fac": store.create_user("fac", "Faculty One", PW, "faculty", "CSE"),
        "hod": store.create_user("hod", "HOD CSE", PW, "hod", "CSE"),
        "hodece": store.create_user("hodece", "HOD ECE", PW, "hod", "ECE"),
    }
    store.import_dir(SAMPLES, owner=users["fac"], department="CSE")
    store.import_programmes(SAMPLES / "programmes")
    app = create_app(store, mailer=None)

    def client(name):
        c = TestClient(app)
        assert c.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
        return c

    return store, users, client


def test_course_carries_its_framework_and_bloom_suggestions(env):
    _, _, client = env
    j = client("fac").get("/api/courses/CSE205").json()
    assert j["framework"]["programme"] == "CSE" and j["framework"]["source"] == "programme"
    assert j["framework"]["outcomes"][-1]["code"] == "PSO2"
    assert j["bloom_suggestions"][0] == "analyse"


def test_validate_draft_switches_framework_with_po_programme(env):
    _, _, client = env
    c = client("fac")
    d = load("CSE205"); d["po_programme"] = "ME"                                # ME has no outcomes of its own
    r = c.post("/api/validate", json=d).json()
    assert r["framework"]["source"] == "locf" and r["framework"]["programme"] == "ME"
    assert {i["rule"] for i in r["issues"]} == {"PO_UNKNOWN"}


def test_submit_is_blocked_by_unknown_programme_outcomes(env):
    _, _, client = env
    fac = client("fac")
    d = load("CSE205"); d["outcomes"][0]["po"]["PO12"] = 2
    fac.put("/api/courses/CSE205", json=d)
    r = fac.post("/api/courses/CSE205/actions/submit", json={"comment": ""})
    assert r.status_code == 422 and r.json()["issues"][0]["rule"] == "PO_UNKNOWN"


def test_programme_list_and_coverage(env):
    _, _, client = env
    c = client("fac")
    rows = {r["code"]: r for r in c.get("/api/programme-outcomes").json()}
    assert set(rows) == {"CSE", "ECE", "ME"}
    assert rows["CSE"]["own"] and rows["CSE"]["outcomes"] == 11 and rows["CSE"]["courses"] == 3
    assert not rows["ME"]["own"] and rows["ME"]["courses"] == 0
    assert rows["CSE"]["can_edit"] is False                                     # faculty
    j = c.get("/api/programme-outcomes/CSE").json()
    assert [x["course_code"] for x in j["courses"]] == ["CSE205", "CSE206", "MTH101"]
    assert j["gaps"] == ["PO6", "PO9"]
    assert j["courses"][0]["levels"]["PSO1"] == 3
    assert c.get("/api/programme-outcomes/ME").json()["framework"]["source"] == "locf"


def test_who_may_edit_programme_outcomes(env):
    _, _, client = env
    body = prog("CSE").model_dump()
    body["outcomes"][0]["text"] = "Changed."
    assert client("fac").put("/api/programme-outcomes/CSE", json=body).status_code == 403
    assert client("hodece").put("/api/programme-outcomes/CSE", json=body).status_code == 403
    hod = client("hod")
    assert hod.put("/api/programme-outcomes/CSE", json=body).status_code == 200
    assert hod.put("/api/programme-outcomes/CSE", json={**body, "department": "ECE"}).status_code == 403
    assert hod.put("/api/programme-outcomes/CSE", json={**body, "code": "XYZ"}).status_code == 400
    assert client("admin").put("/api/programme-outcomes/CSE", json={**body, "department": "ECE"}).status_code == 200
    assert hod.get("/api/programme-outcomes/CSE").json()["can_edit"] is False     # now ECE's


def test_hod_sets_up_a_new_programme_from_locf(env):
    _, _, client = env
    hod = client("hod")
    locf = hod.get("/api/frameworks/locf").json()
    assert len(locf["outcomes"]) == 9 and "LOCF" in locf["source_label"]
    body = {"code": "ME", "name": "B.Tech. ME", "department": "CSE", "outcomes": locf["outcomes"]}
    assert hod.put("/api/programme-outcomes/ME", json={**body, "department": "ME"}).status_code == 403
    r = hod.put("/api/programme-outcomes/ME", json=body)
    assert r.status_code == 200 and r.json()["framework"]["source"] == "programme"


def test_duplicate_or_malformed_outcome_codes_are_refused(env):
    _, _, client = env
    admin = client("admin")
    body = prog("CSE").model_dump()
    body["outcomes"][1]["code"] = "PO1"
    r = admin.put("/api/programme-outcomes/CSE", json=body)
    assert r.status_code == 400 and "PO1" in r.json()["detail"]
    body["outcomes"][1]["code"] = "po 2"
    assert admin.put("/api/programme-outcomes/CSE", json=body).status_code == 422


def test_course_docx_from_the_api_has_the_programme_columns(env):
    store, _, client = env
    r = client("fac").get("/api/courses/CSE206/docx")
    assert r.status_code == 200
    tables = [[[c.text for c in row.cells] for row in t.rows] for t in Document(io.BytesIO(r.content)).tables]
    assert any(t[0][:2] == ["CO", "PO1"] and t[0][-1] == "PSO2" for t in tables)

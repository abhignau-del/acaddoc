"""Programme pack: the export other tools read."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acaddoc.api import create_app
from acaddoc.cli import main
from acaddoc.outcomes import framework
from acaddoc.pack import FORMAT, PackItem, build_pack
from acaddoc.schema import Course, ProgrammeRecord
from acaddoc.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
PW = "correct horse"


def course(code: str) -> Course:
    return Course.model_validate_json((SAMPLES / f"{code}.json").read_text(encoding="utf-8"))


def prog(code: str) -> ProgrammeRecord:
    return ProgrammeRecord.model_validate_json((SAMPLES / "programmes" / f"{code}.json").read_text(encoding="utf-8"))


def test_pack_shape_order_and_foreign_links():
    items = [PackItem(course(c)) for c in ("CSE206", "ENG103", "MTH101", "CSE205")]
    p = build_pack("CSE", framework("CSE", prog("CSE")), items, basis="current", department="CSE")
    assert p["format"] == FORMAT and p["version"] == 1 and p["basis"] == "current"
    assert p["programme"]["source"] == "programme" and p["programme"]["department"] == "CSE"
    assert [o["code"] for o in p["programme"]["outcomes"]][-2:] == ["PSO1", "PSO2"]
    assert [(c["course"]["course_code"], c["semester"]) for c in p["courses"]] == [
        ("MTH101", "I"), ("ENG103", "II"), ("CSE205", "III"), ("CSE206", "III")]
    eng = next(c for c in p["courses"] if c["course"]["course_code"] == "ENG103")
    assert eng["mapped_to"] == "ECE" and all(o["po"] == {} for o in eng["course"]["outcomes"])
    assert eng["course"]["outcomes"][0]["bloom"]                                  # Bloom levels kept
    assert p["notes"] == ["ENG103 is mapped to the outcomes of ECE; its CO-PO links are left out."]
    cse = next(c for c in p["courses"] if c["course"]["course_code"] == "CSE205")
    assert cse["course"]["outcomes"][0]["po"] == {"PO1": 3, "PO2": 3, "PSO1": 2}
    Course.model_validate(cse["course"])                                         # still an AcadDoc course


def test_pack_without_own_outcomes_says_locf():
    p = build_pack("ME", framework("ME", None), [PackItem(course("MTH101"))])
    assert p["programme"]["source"] == "locf" and p["programme"]["outcomes"][0]["code"] == "GA1"


def test_pack_is_plain_json(tmp_path):
    out = tmp_path / "p.json"
    assert main(["pack", str(SAMPLES), "--programmes", str(SAMPLES / "programmes"), "--programme", "CSE",
                 "-o", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["courses"]) == 4 and data["programme"]["name"].startswith("B.Tech.")
    assert main(["pack", str(SAMPLES), "--programme", "MBA", "-o", str(tmp_path / "x.json")]) == 1


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "t.db")
    users = {"fac": store.create_user("fac", "Faculty One", PW, "faculty", "CSE"),
             "hod": store.create_user("hod", "HOD CSE", PW, "hod", "CSE"),
             "dean": store.create_user("dean", "Dean", PW, "dean")}
    store.import_dir(SAMPLES, owner=users["fac"], department="CSE")
    store.import_programmes(SAMPLES / "programmes")
    app = create_app(store, mailer=None)

    def login(name):
        c = TestClient(app)
        assert c.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
        return c
    return login


def test_api_pack_uses_approved_versions_and_lists_the_rest(client):
    fac, hod, dean = client("fac"), client("hod"), client("dean")
    for c, a in ((fac, "submit"), (hod, "hod_approve"), (dean, "approve")):
        assert c.post("/api/courses/CSE205/actions/" + a, json={"comment": ""}).status_code == 200
    fac.post("/api/courses/CSE205/actions/reopen", json={"comment": ""})
    d = course("CSE205").model_dump(); d["course_title"] = "Unapproved Draft Title"
    fac.put("/api/courses/CSE205", json=d)

    r = fac.get("/api/programme-pack", params={"programme": "CSE"})
    assert r.status_code == 200 and 'filename="AcadDoc_CSE_pack.json"' in r.headers["content-disposition"]
    p = r.json()
    assert p["basis"] == "approved"
    assert [(c["course"]["course_code"], c["status"], c["version"]) for c in p["courses"]] == [("CSE205", "approved", 1)]
    assert p["courses"][0]["course"]["course_title"] == "Data Structures"            # the approved text
    assert {x["course_code"] for x in p["left_out"]} == {"MTH101", "ENG103", "CSE206"}
    assert "not approved yet" in p["left_out"][0]["reason"]

    p = fac.get("/api/programme-pack", params={"programme": "CSE", "include_drafts": True}).json()
    assert p["basis"] == "current" and len(p["courses"]) == 4 and p["left_out"] == []
    assert next(c for c in p["courses"] if c["course"]["course_code"] == "CSE205")["course"]["course_title"] \
        == "Unapproved Draft Title"


def test_api_pack_errors_and_sign_in(client, tmp_path):
    fac = client("fac")
    assert fac.get("/api/programme-pack", params={"programme": "MBA"}).status_code == 404
    assert TestClient(fac.app).get("/api/programme-pack", params={"programme": "CSE"}).status_code == 401
    r = fac.get("/api/programme-pack", params={"programme": "CSE (AI & ML)"})
    assert r.status_code == 404                                                      # nothing offered to it

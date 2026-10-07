"""The HTTP API the editor talks to."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from acaddoc.api import create_app
from acaddoc.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def sample(code: str) -> dict:
    return json.loads((SAMPLES / f"{code}.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "t.db")
    store.import_dir(SAMPLES)
    return TestClient(create_app(store))


def test_list_shows_every_course_with_issue_counts(client):
    rows = client.get("/api/courses").json()
    assert [r["course_code"] for r in rows] == ["CSE205", "CSE206", "ENG103", "MTH101"]
    assert all(r["errors"] == 0 for r in rows)


def test_get_returns_course_and_issues(client):
    r = client.get("/api/courses/MTH101").json()
    assert r["course"]["course_title"] == "Linear Algebra and Calculus" and r["issues"] == []
    assert client.get("/api/courses/NOPE1").status_code == 404


def test_create_then_duplicate_is_conflict(client):
    d = sample("MTH101"); d["course_code"] = "MTH102"
    assert client.post("/api/courses", json=d).status_code == 201
    assert client.post("/api/courses", json=d).status_code == 409


def test_structurally_invalid_course_is_not_stored(client):
    d = sample("MTH101"); d["course_code"] = "MTH103"; d["hours"]["credits"] = "four"
    assert client.post("/api/courses", json=d).status_code == 422
    assert client.get("/api/courses/MTH103").status_code == 404


@pytest.mark.parametrize("code", ["", "M", "mth 1", "../X", "A" * 17])
def test_bad_course_codes_are_rejected(client, code):
    d = sample("MTH101"); d["course_code"] = code
    assert client.post("/api/courses", json=d).status_code == 422


def test_rule_violations_are_saved_but_block_the_document(client):
    d = sample("CSE205"); d["modules"] = d["modules"][:3]
    r = client.put("/api/courses/CSE205", json=d)
    assert r.status_code == 200
    assert "MODULE_COUNT" in {i["rule"] for i in r.json()["issues"]}
    blocked = client.get("/api/courses/CSE205/docx")
    assert blocked.status_code == 422 and blocked.json()["issues"]
    forced = client.get("/api/courses/CSE205/docx?force=true")
    assert forced.status_code == 200


def test_rename_by_changing_the_code(client):
    d = sample("CSE206"); d["course_code"] = "CSE216"
    assert client.put("/api/courses/CSE206", json=d).status_code == 200
    assert client.get("/api/courses/CSE206").status_code == 404
    assert client.get("/api/courses/CSE216").status_code == 200
    d["course_code"] = "MTH101"   # onto an existing course
    assert client.put("/api/courses/CSE216", json=d).status_code == 409


def test_delete(client):
    assert client.delete("/api/courses/ENG103").status_code == 204
    assert client.delete("/api/courses/ENG103").status_code == 404


def test_validate_reports_structure_problems_as_data(client):
    d = sample("MTH101"); del d["overview"]; d["marks"]["cia"] = "x"
    r = client.post("/api/validate", json=d).json()
    assert {s["where"] for s in r["structure"]} == {"overview", "marks.cia"}
    d = sample("MTH101"); d["marks"]["total"] = 99
    r = client.post("/api/validate", json=d).json()
    assert r["structure"] == [] and r["issues"][0]["rule"] == "MARKS_TOTAL"


def test_docx_download_is_a_real_document(client):
    r = client.get("/api/courses/MTH101/docx")
    assert r.status_code == 200
    assert "MTH101.docx" in r.headers["content-disposition"]
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "MODULE – I: MATRICES (10)" in text


def test_programmes_and_handbook(client):
    assert client.get("/api/programmes").json() == ["CSE", "ECE", "ME"]
    d = sample("CSE205"); d["modules"][0]["hours"] += 1
    client.put("/api/courses/CSE205", json=d)
    r = client.get("/api/handbook", params={"programme": "CSE", "year": "2026-27"})
    assert r.status_code == 200 and r.headers["x-excluded-courses"] == "CSE205"
    r = client.get("/api/handbook", params={"programme": "CSE", "year": "2026-27", "include_invalid": True})
    assert r.headers["x-excluded-courses"] == ""
    assert client.get("/api/handbook", params={"programme": "MBA", "year": "2026-27"}).status_code == 404

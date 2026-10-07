"""The HTTP API, signed in as each role."""
from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from acaddoc.api import create_app
from acaddoc.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
PW = "correct horse"


def sample(code: str) -> dict:
    return json.loads((SAMPLES / f"{code}.json").read_text(encoding="utf-8"))


@pytest.fixture
def env(tmp_path):
    """A store with one user per role; the samples belong to `fac` in CSE."""
    store = Store(tmp_path / "t.db")
    users = {
        "admin": store.create_user("admin", "Admin", PW, "admin"),
        "fac": store.create_user("fac", "Faculty One", PW, "faculty", "CSE"),
        "fac2": store.create_user("fac2", "Faculty Two", PW, "faculty", "CSE"),
        "hod": store.create_user("hod", "HOD CSE", PW, "hod", "CSE"),
        "hodece": store.create_user("hodece", "HOD ECE", PW, "hod", "ECE"),
        "dean": store.create_user("dean", "Dean", PW, "dean"),
    }
    store.import_dir(SAMPLES, owner=users["fac"], department="CSE")
    app = create_app(store)

    def client(name: str | None = None) -> TestClient:
        c = TestClient(app)
        if name:
            assert c.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
        return c

    return store, users, client


def act(c, code, action, comment=""):
    return c.post(f"/api/courses/{code}/actions/{action}", json={"comment": comment})


# --- sign-in ------------------------------------------------------------------------------

def test_everything_needs_sign_in(env):
    _, _, client = env
    anon = client()
    for path in ("/api/courses", "/api/courses/MTH101", "/api/users", "/api/programmes",
                 "/api/courses/MTH101/docx", "/api/courses/MTH101/history"):
        assert anon.get(path).status_code == 401, path
    assert anon.post("/api/validate", json={}).status_code == 401
    assert anon.get("/api/health").status_code == 200


def test_first_run_setup_creates_the_admin_once(tmp_path):
    c = TestClient(create_app(Store(tmp_path / "new.db")))
    assert c.get("/api/auth/state").json()["needs_setup"] is True
    r = c.post("/api/auth/setup", json={"username": "Boss", "display_name": "The Boss", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin" and r.json()["user"]["username"] == "boss"
    assert c.get("/api/auth/state").json()["user"]["username"] == "boss"   # signed in by the cookie
    assert c.post("/api/auth/setup", json={"username": "evil", "display_name": "E", "password": PW}).status_code == 409


def test_login_logout_and_wrong_password(env):
    _, _, client = env
    c = client()
    assert c.post("/api/auth/login", json={"username": "fac", "password": "nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "ghost", "password": PW}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "FAC ", "password": PW})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert c.get("/api/courses").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/courses").status_code == 401


def test_repeated_failures_are_throttled(env):
    _, _, client = env
    c = client()
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "fac", "password": "wrong-wrong"})
    assert c.post("/api/auth/login", json={"username": "fac", "password": PW}).status_code == 429


def test_cross_site_writes_are_refused(env):
    _, _, client = env
    c = client("fac")
    d = sample("CSE205")
    r = c.put("/api/courses/CSE205", json=d, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert c.put("/api/courses/CSE205", json=d, headers={"Origin": "http://testserver"}).status_code == 200


def test_changing_password_signs_out_everywhere(env):
    _, _, client = env
    a, b = client("fac"), client("fac")
    assert a.post("/api/auth/password", json={"current_password": "bad", "new_password": "another pw"}).status_code == 400
    assert a.post("/api/auth/password", json={"current_password": PW, "new_password": "short"}).status_code == 400
    assert a.post("/api/auth/password", json={"current_password": PW, "new_password": "another pw"}).status_code == 204
    assert b.get("/api/courses").status_code == 401
    c = client()
    assert c.post("/api/auth/login", json={"username": "fac", "password": "another pw"}).status_code == 200


# --- users -------------------------------------------------------------------------------

def test_only_admin_manages_users(env):
    _, users, client = env
    fac, admin = client("fac"), client("admin")
    body = {"username": "newbie", "display_name": "New", "password": PW, "role": "faculty", "department": "ECE"}
    assert fac.post("/api/users", json=body).status_code == 403
    assert admin.post("/api/users", json=body).status_code == 201
    assert admin.post("/api/users", json=body).status_code == 409
    assert admin.post("/api/users", json={**body, "username": "x2", "role": "king"}).status_code == 400
    assert fac.patch(f"/api/users/{users['fac2'].id}", json={"role": "dean"}).status_code == 403


def test_disabling_a_user_signs_them_out(env):
    _, users, client = env
    fac2, admin = client("fac2"), client("admin")
    assert admin.patch(f"/api/users/{users['fac2'].id}", json={"disabled": True}).status_code == 200
    assert fac2.get("/api/courses").status_code == 401
    assert client().post("/api/auth/login", json={"username": "fac2", "password": PW}).status_code == 401


def test_the_last_admin_cannot_be_removed(env):
    _, users, client = env
    admin = client("admin")
    assert admin.patch(f"/api/users/{users['admin'].id}", json={"role": "faculty"}).status_code == 409
    assert admin.patch(f"/api/users/{users['admin'].id}", json={"disabled": True}).status_code == 409


# --- course editing ------------------------------------------------------------------------

def test_list_shows_status_and_owner(env):
    _, _, client = env
    rows = client("fac").get("/api/courses").json()
    assert [r["course_code"] for r in rows] == ["CSE205", "CSE206", "ENG103", "MTH101"]
    assert {(r["status"], r["owner_name"], r["department"]) for r in rows} == {("draft", "Faculty One", "CSE")}


def test_new_course_belongs_to_its_author_and_their_department(env):
    _, _, client = env
    d = sample("MTH101"); d["course_code"] = "ECE301"
    admin = client("admin")
    admin.post("/api/users", json={"username": "ecefac", "display_name": "ECE Fac", "password": PW,
                                   "role": "faculty", "department": "ECE"})
    r = client("ecefac").post("/api/courses", json=d)
    assert r.status_code == 201
    j = r.json()
    assert j["owner_name"] == "ECE Fac" and j["department"] == "ECE" and j["can"]["edit"]


def test_only_owner_or_admin_can_edit(env):
    _, _, client = env
    d = sample("CSE205"); d["course_title"] = "Changed"
    assert client("fac2").put("/api/courses/CSE205", json=d).status_code == 403
    assert client("hod").put("/api/courses/CSE205", json=d).status_code == 403
    assert client("fac").put("/api/courses/CSE205", json=d).status_code == 200
    assert client("admin").put("/api/courses/CSE205", json=d).status_code == 200


def test_bad_course_codes_are_rejected(env):
    _, _, client = env
    c = client("fac")
    for code in ["", "M", "mth 1", "../X", "A" * 17]:
        d = sample("MTH101"); d["course_code"] = code
        assert c.post("/api/courses", json=d).status_code == 422, code


def test_validate_reports_structure_problems_as_data(env):
    _, _, client = env
    c = client("fac")
    d = sample("MTH101"); del d["overview"]; d["marks"]["cia"] = "x"
    r = c.post("/api/validate", json=d).json()
    assert {s["where"] for s in r["structure"]} == {"overview", "marks.cia"}
    d = sample("MTH101"); d["marks"]["total"] = 99
    r = c.post("/api/validate", json=d).json()
    assert r["structure"] == [] and r["issues"][0]["rule"] == "MARKS_TOTAL"


def test_docx_download_is_a_real_document(env):
    _, _, client = env
    r = client("dean").get("/api/courses/MTH101/docx")   # anyone signed in may read
    assert r.status_code == 200 and "MTH101.docx" in r.headers["content-disposition"]
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "MODULE – I: MATRICES (10)" in text


# --- the workflow --------------------------------------------------------------------------

def test_full_approval_path_with_one_revision(env):
    _, _, client = env
    fac, hod, dean = client("fac"), client("hod"), client("dean")

    assert act(fac, "CSE205", "submit").json()["status"] == "submitted"
    d = sample("CSE205"); d["course_title"] = "Too late"
    assert fac.put("/api/courses/CSE205", json=d).status_code == 403          # frozen while in review

    assert act(hod, "CSE205", "request_revision").status_code == 400           # a reason is required
    r = act(hod, "CSE205", "request_revision", "Add a module on hashing.")
    assert r.json()["status"] == "revision_required"

    d = sample("CSE205"); d["modules"][4]["title"] = "Hashing"
    assert fac.put("/api/courses/CSE205", json=d).status_code == 200
    assert act(fac, "CSE205", "submit").json()["version"] == 2
    assert act(dean, "CSE205", "approve").status_code == 403                   # the HOD goes first
    assert act(hod, "CSE205", "hod_approve").json()["status"] == "hod_approved"
    r = act(dean, "CSE205", "approve").json()
    assert r["status"] == "approved" and r["approved_version"] == 2 and r["can"]["edit"] is False

    h = fac.get("/api/courses/CSE205/history").json()
    assert [e["action"] for e in h["events"]] == [
        "create", "submit", "request_revision", "submit", "hod_approve", "approve"]
    assert h["events"][2]["comment"] == "Add a module on hashing." and h["events"][2]["user_name"] == "HOD CSE"
    assert [v["version"] for v in h["versions"]] == [1, 2]


def test_approved_version_stays_in_force_while_the_next_is_drafted(env):
    _, _, client = env
    fac, hod, dean = client("fac"), client("hod"), client("dean")
    for c, a in ((fac, "submit"), (hod, "hod_approve"), (dean, "approve")):
        assert act(c, "MTH101", a).status_code == 200
    assert act(fac, "MTH101", "reopen").json()["status"] == "draft"
    d = sample("MTH101"); d["course_title"] = "Linear Algebra, Calculus and More"
    assert fac.put("/api/courses/MTH101", json=d).status_code == 200

    old = fac.get("/api/courses/MTH101/versions/1/docx")
    texts = [c.text for t in Document(io.BytesIO(old.content)).tables for row in t.rows for c in row.cells]
    assert "LINEAR ALGEBRA AND CALCULUS" in texts                               # v1 untouched
    j = fac.get("/api/courses/MTH101").json()
    assert j["approved_version"] == 1 and j["course"]["course_title"].endswith("More")
    assert fac.get("/api/courses/MTH101/versions/9/docx").status_code == 404


def test_submit_is_refused_while_rules_fail(env):
    _, _, client = env
    fac = client("fac")
    d = sample("CSE205"); d["modules"] = d["modules"][:3]
    fac.put("/api/courses/CSE205", json=d)
    r = act(fac, "CSE205", "submit")
    assert r.status_code == 422 and r.json()["issues"][0]["rule"] == "MODULE_COUNT"


def test_wrong_department_hod_and_self_review_are_refused(env):
    store, users, client = env
    fac, hodece = client("fac"), client("hodece")
    act(fac, "CSE205", "submit")
    assert act(hodece, "CSE205", "hod_approve").status_code == 403
    store.set_meta("ENG103", owner_id=users["hod"].id)
    hod = client("hod")
    act(hod, "ENG103", "submit")
    r = act(hod, "ENG103", "hod_approve")
    assert r.status_code == 403 and "own" in r.json()["detail"]


def test_withdraw_returns_to_draft(env):
    _, _, client = env
    fac = client("fac")
    act(fac, "CSE206", "submit")
    assert act(fac, "CSE206", "withdraw").json()["status"] == "draft"
    assert act(fac, "CSE206", "withdraw").status_code == 403


def test_two_reviewers_racing_get_a_conflict(env):
    store, users, client = env
    fac, hod = client("fac"), client("hod")
    act(fac, "CSE205", "submit")
    # someone else acts between this request's read and write
    with pytest.raises(Exception):
        store.transition("CSE205", "hod_approve", expect="draft", to="hod_approved", by=users["hod"])
    assert act(hod, "CSE205", "hod_approve").status_code == 200


def test_submitted_course_keeps_code_and_cannot_be_deleted(env):
    _, _, client = env
    fac = client("fac")
    act(fac, "CSE206", "submit"); act(fac, "CSE206", "withdraw")
    d = sample("CSE206"); d["course_code"] = "CSE216"
    assert fac.put("/api/courses/CSE206", json=d).status_code == 409
    assert fac.delete("/api/courses/CSE206").status_code == 403
    assert fac.delete("/api/courses/ENG103").status_code == 204                # never submitted
    assert client("fac2").delete("/api/courses/MTH101").status_code == 403


def test_rename_a_never_submitted_course(env):
    _, _, client = env
    fac = client("fac")
    d = sample("CSE206"); d["course_code"] = "CSE216"
    assert fac.put("/api/courses/CSE206", json=d).status_code == 200
    assert fac.get("/api/courses/CSE206").status_code == 404
    assert fac.get("/api/courses/CSE216/history").json()["events"][0]["action"] == "create"


def test_admin_reassigns_owner_and_department(env):
    _, users, client = env
    admin, fac2 = client("admin"), client("fac2")
    assert client("fac").patch("/api/courses/CSE205/meta", json={"owner_id": users["fac2"].id}).status_code == 403
    r = admin.patch("/api/courses/CSE205/meta", json={"owner_id": users["fac2"].id, "department": "ECE"})
    assert r.json()["owner_name"] == "Faculty Two" and r.json()["department"] == "ECE"
    assert fac2.get("/api/courses/CSE205").json()["can"]["edit"] is True


def test_awaiting_me_marks_the_review_queue(env):
    _, _, client = env
    act(client("fac"), "CSE205", "submit")
    mine = {r["course_code"] for r in client("hod").get("/api/courses").json() if r["awaiting_me"]}
    assert mine == {"CSE205"}
    assert not any(r["awaiting_me"] for r in client("hodece").get("/api/courses").json())


# --- handbook ------------------------------------------------------------------------------

def test_handbook_uses_approved_versions_only(env):
    _, _, client = env
    fac, hod, dean = client("fac"), client("hod"), client("dean")
    q = {"programme": "CSE", "year": "2026-27"}
    assert fac.get("/api/handbook", params=q).status_code == 404               # nothing approved yet
    for c, a in ((fac, "submit"), (hod, "hod_approve"), (dean, "approve")):
        act(c, "MTH101", a)
    act(fac, "MTH101", "reopen")
    d = sample("MTH101"); d["course_title"] = "Draft Title Not Approved"
    fac.put("/api/courses/MTH101", json=d)

    r = fac.get("/api/handbook", params=q)
    assert r.status_code == 200
    assert set(r.headers["x-unapproved-courses"].split(",")) == {"CSE205", "CSE206", "ENG103"}
    text = "\n".join(c.text for t in Document(io.BytesIO(r.content)).tables for row in t.rows for c in row.cells)
    assert "LINEAR ALGEBRA AND CALCULUS" in text and "DRAFT TITLE" not in text

    r = fac.get("/api/handbook", params={**q, "include_unapproved": True})
    assert r.headers["x-unapproved-courses"] == ""
    assert client("fac").get("/api/handbook", params={"programme": "MBA", "year": "2026-27"}).status_code == 404


def test_programmes(env):
    _, _, client = env
    assert client("fac").get("/api/programmes").json() == ["CSE", "ECE", "ME"]


# --- upgrading a v0.1.0 database -------------------------------------------------------------

def test_v010_database_is_upgraded_in_place(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE courses (code TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)")
    db.execute("INSERT INTO courses VALUES (?, ?, ?)",
               ("MTH101", (SAMPLES / "MTH101.json").read_text(encoding="utf-8"), "2026-10-07T00:00:00+00:00"))
    db.commit(); db.close()
    r = Store(path).get("MTH101")
    assert r.meta.status == "draft" and r.meta.owner_id is None and r.course.course_code == "MTH101"

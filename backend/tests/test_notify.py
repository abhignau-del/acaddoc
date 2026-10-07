"""Email notifications: who is told, what they read, and that mail trouble never blocks the workflow."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acaddoc import notify
from acaddoc.api import create_app
from acaddoc.notify import Mail, SmtpMailer
from acaddoc.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
PW = "correct horse"


class FakeMailer:
    def __init__(self, fail: bool = False):
        self.sent: list[Mail] = []
        self.fail = fail

    def send(self, mail: Mail) -> None:
        if self.fail:
            raise ConnectionRefusedError("mail server down")
        self.sent.append(mail)

    def to(self) -> list[str]:
        return [m.to for m in self.sent]


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    mk = store.create_user
    users = {
        "admin": mk("admin", "Admin", PW, "admin", email="admin@uni.test"),
        "fac": mk("fac", "Faculty One", PW, "faculty", "CSE", email="fac@uni.test"),
        "hod": mk("hod", "HOD CSE", PW, "hod", "CSE", email="hod@uni.test"),
        "hod2": mk("hod2", "Second HOD CSE", PW, "hod", "CSE", email="hod2@uni.test"),
        "hodece": mk("hodece", "HOD ECE", PW, "hod", "ECE", email="hodece@uni.test"),
        "dean": mk("dean", "The Dean", PW, "dean", email="dean@uni.test"),
        "nomail": mk("nomail", "Dean Without Email", PW, "dean"),
    }
    store.import_dir(SAMPLES, owner=users["fac"], department="CSE")
    mailer = FakeMailer()
    app = create_app(store, mailer=mailer, public_url="https://acaddoc.uni.test/")

    def client(name=None):
        c = TestClient(app)
        if name:
            assert c.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
        return c

    return store, users, client, mailer, app


def act(c, code, action, comment=""):
    r = c.post(f"/api/courses/{code}/actions/{action}", json={"comment": comment})
    assert r.status_code == 200, r.text
    return r


def test_each_step_reaches_the_right_people(env):
    store, users, client, mailer, _ = env
    fac, hod, dean = client("fac"), client("hod"), client("dean")

    act(fac, "CSE205", "submit")
    assert sorted(mailer.to()) == ["hod2@uni.test", "hod@uni.test"]          # both CSE HODs, not ECE
    mailer.sent.clear()

    act(hod, "CSE205", "request_revision", "Add hashing.\nAnd tries.")
    assert mailer.to() == ["fac@uni.test"]
    body = mailer.sent[0].body
    assert "    Add hashing.\n    And tries." in body and "HOD CSE" in body
    assert "https://acaddoc.uni.test/#course=CSE205" in body
    mailer.sent.clear()

    act(fac, "CSE205", "submit"); mailer.sent.clear()
    act(hod, "CSE205", "hod_approve")
    assert mailer.to() == ["dean@uni.test"]                                    # the dean without an address is skipped
    assert "final approval" in mailer.sent[0].subject
    mailer.sent.clear()

    act(dean, "CSE205", "approve")
    assert mailer.to() == ["fac@uni.test"] and "is approved" in mailer.sent[0].subject
    mailer.sent.clear()

    act(fac, "CSE205", "reopen")
    assert mailer.sent == []                                                   # nothing to tell anyone


def test_withdraw_tells_the_hods(env):
    _, _, client, mailer, _ = env
    fac = client("fac")
    act(fac, "CSE206", "submit"); mailer.sent.clear()
    act(fac, "CSE206", "withdraw")
    assert sorted(mailer.to()) == ["hod2@uni.test", "hod@uni.test"]
    assert "withdrawn" in mailer.sent[0].subject


def test_nobody_is_told_about_their_own_action(env):
    store, users, client, mailer, _ = env
    store.set_meta("ENG103", owner_id=users["hod"].id)
    act(client("hod"), "ENG103", "submit")
    assert mailer.to() == ["hod2@uni.test"]


def test_disabled_users_get_nothing(env):
    store, users, client, mailer, _ = env
    store.update_user(users["hod2"].id, disabled=True)
    act(client("fac"), "CSE205", "submit")
    assert mailer.to() == ["hod@uni.test"]


def test_every_message_is_logged_as_sent(env):
    store, _, client, mailer, _ = env
    act(client("fac"), "CSE205", "submit")
    log = store.outbox()
    assert {(m["to_addr"], m["status"]) for m in log} == {("hod@uni.test", "sent"), ("hod2@uni.test", "sent")}
    assert all(m["sent_at"] for m in log)


def test_a_broken_mail_server_does_not_block_the_workflow(env):
    store, _, client, _, app = env
    app.state.mailer = FakeMailer(fail=True)
    r = act(client("fac"), "CSE205", "submit")
    assert r.json()["status"] == "submitted"
    log = store.outbox()
    assert {m["status"] for m in log} == {"failed"} and "mail server down" in log[0]["error"]

    app.state.mailer = good = FakeMailer()                                     # the server is back: retry
    admin = client("admin")
    assert client("fac").post(f"/api/admin/mail/{log[0]['id']}/retry").status_code == 403
    r = admin.post(f"/api/admin/mail/{log[0]['id']}/retry")
    assert r.json()["status"] == "sent" and len(good.sent) == 1
    assert admin.post(f"/api/admin/mail/{log[0]['id']}/retry").status_code == 409


def test_without_mail_settings_messages_are_recorded_not_sent(env):
    store, _, client, _, app = env
    app.state.mailer = None
    act(client("fac"), "CSE205", "submit")
    assert {m["status"] for m in store.outbox()} == {"not_configured"}
    status = client("admin").get("/api/admin/mail").json()
    assert status["configured"] is False and len(status["outbox"]) == 2


def test_admin_mail_page_and_test_email(env):
    _, users, client, mailer, app = env
    admin = client("admin")
    assert client("dean").get("/api/admin/mail").status_code == 403
    r = admin.post("/api/admin/mail/test")
    assert r.json()["status"] == "sent" and mailer.to() == ["admin@uni.test"]
    status = admin.get("/api/admin/mail").json()
    assert status["public_url"] == "https://acaddoc.uni.test/" and status["outbox"][0]["subject"] == "[AcadDoc] Test email"

    app.state.mailer = None
    assert admin.post("/api/admin/mail/test").status_code == 409


def test_users_manage_their_own_address(env):
    _, users, client, _, _ = env
    fac = client("fac")
    assert fac.patch("/api/auth/me", json={"email": "not-an-address"}).status_code == 400
    r = fac.patch("/api/auth/me", json={"email": " new@uni.test "})
    assert r.json()["user"]["email"] == "new@uni.test"
    assert fac.patch("/api/auth/me", json={"email": ""}).json()["user"]["email"] == ""   # opt out
    admin = client("admin")
    assert admin.patch(f"/api/users/{users['fac'].id}", json={"email": "x@"}).status_code == 400
    assert admin.post("/api/users", json={"username": "zed9", "display_name": "Z", "password": PW,
                                          "role": "faculty", "email": "zed9@uni.test"}).json()["email"] == "zed9@uni.test"


def test_no_public_url_means_no_link(env):
    store, users, _, _, _ = env
    r = store.get("CSE205")
    m = notify.compose("approve", r, users["dean"], users["fac"], "", "")
    assert "Open the course" not in m.body and m.to == "fac@uni.test"


# --- SMTP --------------------------------------------------------------------------------

def test_settings_from_environment():
    assert SmtpMailer.from_env({}) is None
    m = SmtpMailer.from_env({"ACADDOC_SMTP_HOST": "smtp.uni.test", "ACADDOC_SMTP_USER": "bot@uni.test",
                             "ACADDOC_SMTP_PASSWORD": "pw"})
    assert (m.port, m.security, m.sender) == (587, "starttls", "bot@uni.test")
    m = SmtpMailer.from_env({"ACADDOC_SMTP_HOST": "h", "ACADDOC_SMTP_SECURITY": "SSL", "ACADDOC_MAIL_FROM": "a@b.c"})
    assert (m.port, m.security, m.sender) == (465, "ssl", "a@b.c")
    assert "password" not in m.describe()
    with pytest.raises(ValueError):
        SmtpMailer.from_env({"ACADDOC_SMTP_HOST": "h", "ACADDOC_SMTP_SECURITY": "tls1"})


class FakeSMTP:
    calls: list = []

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.calls.append(("connect", host, port, "ssl" if context else "plain"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        FakeSMTP.calls.append(("quit",))

    def starttls(self, context=None):
        FakeSMTP.calls.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.calls.append(("login", user))

    def send_message(self, msg):
        FakeSMTP.calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))


@pytest.mark.parametrize("security,expect", [
    ("starttls", ["connect-plain", "starttls", "login", "send", "quit"]),
    ("ssl", ["connect-ssl", "login", "send", "quit"]),
    ("none", ["connect-plain", "send", "quit"]),
])
def test_smtp_conversation(monkeypatch, security, expect):
    FakeSMTP.calls = []
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    user = "" if security == "none" else "bot@uni.test"
    SmtpMailer("smtp.uni.test", 25, user, "pw", security, "bot@uni.test").send(Mail("a@uni.test", "Hi", "Body"))
    steps = [c[0] + ("-" + c[3] if c[0] == "connect" else "") for c in FakeSMTP.calls]
    assert steps == expect
    assert ("send", "bot@uni.test", "a@uni.test", "Hi", "Body") in FakeSMTP.calls


# --- upgrading a v0.2.0 database ------------------------------------------------------------

def test_v020_users_table_gains_email(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,"
               " password_hash TEXT NOT NULL, role TEXT NOT NULL, department TEXT NOT NULL DEFAULT '',"
               " disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
    db.execute("INSERT INTO users VALUES ('u1', 'old', 'Old User', 'x', 'faculty', 'CSE', 0, '2026-10-07')")
    db.commit(); db.close()
    s = Store(path)
    assert s.user("u1").email == ""
    assert s.update_user("u1", email="old@uni.test").email == "old@uni.test"

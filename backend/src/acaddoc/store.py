"""SQLite storage: courses, their frozen versions, the audit trail, users and sessions.

Course content is kept as one validated JSON record (schema.py stays the single
source of truth); the workflow columns sit beside it. Every content write goes
through Course validation, so the table never holds a record the renderer cannot read.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import auth
from .auth import User
from .schema import Course
from .workflow import Meta

DEFAULT_DB = Path(__file__).resolve().parents[2] / "acaddoc.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    code TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_versions (
    code TEXT NOT NULL,
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    PRIMARY KEY (code, version)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    at TEXT NOT NULL,
    user_id TEXT,
    user_name TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    version INTEGER,
    comment TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_code ON events (code, id);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    to_addr TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued, sent, failed, not_configured
    error TEXT NOT NULL DEFAULT '',
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires REAL NOT NULL
);
"""

# Columns added after a release. Older databases are upgraded in place.
_USER_COLUMNS = {"email": "TEXT NOT NULL DEFAULT ''"}
# Columns added to `courses` after v0.1.0.
_COURSE_COLUMNS = {
    "department": "TEXT NOT NULL DEFAULT ''",
    "owner_id": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'draft'",
    "version": "INTEGER NOT NULL DEFAULT 0",
    "approved_version": "INTEGER",
    "updated_by": "TEXT",
}


class NotFound(KeyError):
    pass


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    course: Course
    updated_at: str
    meta: Meta
    owner_name: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get("ACADDOC_DB") or DEFAULT_DB)
        with self._db() as db:
            db.executescript(_SCHEMA)
            have = {r["name"] for r in db.execute("PRAGMA table_info(courses)")}
            for col, decl in _COURSE_COLUMNS.items():
                if col not in have:
                    db.execute(f"ALTER TABLE courses ADD COLUMN {col} {decl}")
            have = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
            for col, decl in _USER_COLUMNS.items():
                if col not in have:
                    db.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # --- courses ------------------------------------------------------------------

    _SELECT = ("SELECT c.*, COALESCE(u.display_name, '') AS owner_name "
               "FROM courses c LEFT JOIN users u ON u.id = c.owner_id")

    @staticmethod
    def _record(row) -> Record:
        meta = Meta(code=row["code"], department=row["department"], owner_id=row["owner_id"],
                    status=row["status"], version=row["version"], approved_version=row["approved_version"])
        return Record(Course.model_validate_json(row["data"]), row["updated_at"], meta, row["owner_name"])

    def list(self) -> list[Record]:
        with self._db() as db:
            return [self._record(r) for r in db.execute(self._SELECT + " ORDER BY c.code")]

    def get(self, code: str) -> Record:
        with self._db() as db:
            row = db.execute(self._SELECT + " WHERE c.code = ?", (code,)).fetchone()
        if not row:
            raise NotFound(code)
        return self._record(row)

    def create(self, c: Course, *, owner: User | None = None, department: str | None = None) -> Record:
        dept = department if department is not None else (owner.department if owner else "")
        with self._db() as db:
            try:
                db.execute("INSERT INTO courses (code, data, updated_at, department, owner_id, updated_by) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (c.course_code, c.model_dump_json(), _now(), dept, owner.id if owner else None,
                            owner.id if owner else None))
            except sqlite3.IntegrityError:
                raise Conflict(f"{c.course_code} already exists") from None
            self._event(db, c.course_code, owner, "create", None, "draft", 0)
        return self.get(c.course_code)

    def update(self, code: str, c: Course, *, by: User | None = None) -> Record:
        """Replace the content of course `code`. Changing course_code renames a never-submitted course."""
        with self._db() as db:
            row = db.execute("SELECT version FROM courses WHERE code = ?", (code,)).fetchone()
            if not row:
                raise NotFound(code)
            if c.course_code != code:
                if row["version"] > 0:
                    raise Conflict("a submitted course keeps its code; create a new course instead")
                if db.execute("SELECT 1 FROM courses WHERE code = ?", (c.course_code,)).fetchone():
                    raise Conflict(f"{c.course_code} already exists")
                db.execute("UPDATE events SET code = ? WHERE code = ?", (c.course_code, code))
            db.execute("UPDATE courses SET code = ?, data = ?, updated_at = ?, updated_by = ? WHERE code = ?",
                       (c.course_code, c.model_dump_json(), _now(), by.id if by else None, code))
        return self.get(c.course_code)

    def set_meta(self, code: str, *, department: str | None = None, owner_id: str | None = None,
                 by: User | None = None) -> Record:
        with self._db() as db:
            if not db.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone():
                raise NotFound(code)
            notes = []
            if department is not None:
                db.execute("UPDATE courses SET department = ? WHERE code = ?", (department, code))
                notes.append(f"department: {department or '(none)'}")
            if owner_id is not None:
                owner = db.execute("SELECT display_name FROM users WHERE id = ?", (owner_id,)).fetchone()
                if not owner:
                    raise NotFound(owner_id)
                db.execute("UPDATE courses SET owner_id = ? WHERE code = ?", (owner_id, code))
                notes.append(f"owner: {owner['display_name']}")
            if notes:
                self._event(db, code, by, "reassign", None, None, None, "; ".join(notes))
        return self.get(code)

    def delete(self, code: str) -> None:
        with self._db() as db:
            if db.execute("DELETE FROM courses WHERE code = ?", (code,)).rowcount == 0:
                raise NotFound(code)
            db.execute("DELETE FROM events WHERE code = ?", (code,))

    def transition(self, code: str, action: str, *, expect: str, to: str, by: User, comment: str = "") -> Record:
        """Move the course from `expect` to `to`. Fails if someone changed its state meanwhile.

        submit freezes the current content as the next version; approve puts that version in force.
        """
        with self._db() as db:
            row = db.execute("SELECT data, status, version FROM courses WHERE code = ?", (code,)).fetchone()
            if not row:
                raise NotFound(code)
            if row["status"] != expect:
                raise Conflict(f"{code} is now {row['status']}; reload and try again")
            version = row["version"]
            if action == "submit":
                version += 1
                db.execute("INSERT INTO course_versions VALUES (?, ?, ?, ?, ?)",
                           (code, version, row["data"], _now(), by.id))
            db.execute("UPDATE courses SET status = ?, version = ? WHERE code = ?", (to, version, code))
            if action == "approve":
                db.execute("UPDATE courses SET approved_version = ? WHERE code = ?", (version, code))
            self._event(db, code, by, action, expect, to, version, comment)
        return self.get(code)

    def version(self, code: str, n: int) -> Course:
        with self._db() as db:
            row = db.execute("SELECT data FROM course_versions WHERE code = ? AND version = ?", (code, n)).fetchone()
        if not row:
            raise NotFound(f"{code} v{n}")
        return Course.model_validate_json(row["data"])

    def history(self, code: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT at, user_name, action, from_status, to_status, version, comment "
                              "FROM events WHERE code = ? ORDER BY id", (code,)).fetchall()
        return [dict(r) for r in rows]

    def versions(self, code: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT v.version, v.created_at, COALESCE(u.display_name, '') AS created_by "
                              "FROM course_versions v LEFT JOIN users u ON u.id = v.created_by "
                              "WHERE v.code = ? ORDER BY v.version", (code,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _event(db, code, by: User | None, action, from_status, to_status, version, comment=""):
        db.execute("INSERT INTO events (code, at, user_id, user_name, action, from_status, to_status, version, comment)"
                   " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (code, _now(), by.id if by else None, by.display_name if by else "system", action,
                    from_status, to_status, version, comment))

    def import_dir(self, folder: Path, *, replace: bool = False, owner: User | None = None,
                   department: str = "") -> list[str]:
        """Load every *.json course in `folder` as drafts. Existing codes are skipped unless replace."""
        done = []
        for f in sorted(Path(folder).glob("*.json")):
            c = Course.model_validate_json(f.read_text(encoding="utf-8"))
            try:
                self.create(c, owner=owner, department=department)
            except Conflict:
                if not replace:
                    continue
                self.update(c.course_code, c, by=owner)
            done.append(c.course_code)
        return done

    # --- users and sessions ---------------------------------------------------------

    def user_count(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def create_user(self, username: str, display_name: str, password: str, role: str,
                    department: str = "", email: str = "") -> User:
        name = auth.normalise_username(username)
        auth.check_password_strength(password)
        if role not in auth.ROLES:
            raise ValueError(f"role must be one of {', '.join(auth.ROLES)}")
        if not display_name.strip():
            raise ValueError("a display name is required")
        email = auth.normalise_email(email)
        uid = uuid.uuid4().hex
        with self._db() as db:
            try:
                db.execute("INSERT INTO users (id, username, display_name, password_hash, role, department,"
                           " disabled, created_at, email) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                           (uid, name, display_name.strip(), auth.hash_password(password), role,
                            department.strip(), _now(), email))
            except sqlite3.IntegrityError:
                raise Conflict(f"the username {name} is taken") from None
        return self.user(uid)

    def user(self, uid: str) -> User:
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise NotFound(uid)
        return auth.user_from_row(row)

    def users(self) -> list[User]:
        with self._db() as db:
            return [auth.user_from_row(r) for r in db.execute("SELECT * FROM users ORDER BY display_name")]

    def credentials(self, username: str) -> tuple[User, str] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        return (auth.user_from_row(row), row["password_hash"]) if row else None

    def update_user(self, uid: str, *, display_name: str | None = None, role: str | None = None,
                    department: str | None = None, disabled: bool | None = None,
                    password: str | None = None, email: str | None = None) -> User:
        sets, args = [], []
        if display_name is not None:
            if not display_name.strip():
                raise ValueError("a display name is required")
            sets.append("display_name = ?"); args.append(display_name.strip())
        if role is not None:
            if role not in auth.ROLES:
                raise ValueError(f"role must be one of {', '.join(auth.ROLES)}")
            sets.append("role = ?"); args.append(role)
        if department is not None:
            sets.append("department = ?"); args.append(department.strip())
        if email is not None:
            sets.append("email = ?"); args.append(auth.normalise_email(email))
        if disabled is not None:
            sets.append("disabled = ?"); args.append(int(disabled))
        if password is not None:
            auth.check_password_strength(password)
            sets.append("password_hash = ?"); args.append(auth.hash_password(password))
        with self._db() as db:
            if not db.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
                raise NotFound(uid)
            if sets:
                db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*args, uid))
            if disabled or password is not None:
                db.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))   # sign out everywhere
        return self.user(uid)

    def active_admins(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0").fetchone()[0]

    def new_session(self, uid: str) -> str:
        token = auth.new_token()
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (auth.token_hash(token), uid, time.time() + auth.SESSION_DAYS * 86400))
        return token

    def session_user(self, token: str) -> User | None:
        with self._db() as db:
            row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                             "WHERE s.token_hash = ? AND s.expires > ?",
                             (auth.token_hash(token), time.time())).fetchone()
        if not row:
            return None
        u = auth.user_from_row(row)
        return None if u.disabled else u

    def end_session(self, token: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (auth.token_hash(token),))

    # --- outgoing email -------------------------------------------------------------

    def queue_mail(self, to_addr: str, subject: str, body: str, *, status: str = "queued") -> int:
        with self._db() as db:
            return db.execute("INSERT INTO outbox (created_at, to_addr, subject, body, status) VALUES (?, ?, ?, ?, ?)",
                              (_now(), to_addr, subject, body, status)).lastrowid

    def mail(self, mid: int) -> dict:
        with self._db() as db:
            row = db.execute("SELECT * FROM outbox WHERE id = ?", (mid,)).fetchone()
        if not row:
            raise NotFound(mid)
        return dict(row)

    def mark_mail(self, mid: int, status: str, error: str = "") -> None:
        with self._db() as db:
            db.execute("UPDATE outbox SET status = ?, error = ?, sent_at = ? WHERE id = ?",
                       (status, error[:500], _now() if status == "sent" else None, mid))

    def outbox(self, limit: int = 100) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT id, created_at, to_addr, subject, status, error, sent_at FROM outbox"
                              " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

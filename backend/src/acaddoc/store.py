"""SQLite storage: one row per course, the validated record kept as JSON.

The schema (schema.py) stays the single source of truth; the database only
keys courses by code and remembers when each changed. Every write goes through
Course validation, so the table never holds a record the renderer cannot read.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schema import Course

DEFAULT_DB = Path(__file__).resolve().parents[2] / "acaddoc.db"


class NotFound(KeyError):
    pass


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get("ACADDOC_DB") or DEFAULT_DB)
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS courses ("
                " code TEXT PRIMARY KEY,"
                " data TEXT NOT NULL,"
                " updated_at TEXT NOT NULL)"
            )

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def list(self) -> list[tuple[Course, str]]:
        with self._db() as db:
            rows = db.execute("SELECT data, updated_at FROM courses ORDER BY code").fetchall()
        return [(Course.model_validate_json(d), u) for d, u in rows]

    def get(self, code: str) -> tuple[Course, str]:
        with self._db() as db:
            row = db.execute("SELECT data, updated_at FROM courses WHERE code = ?", (code,)).fetchone()
        if not row:
            raise NotFound(code)
        return Course.model_validate_json(row[0]), row[1]

    def create(self, c: Course) -> str:
        now = self._now()
        with self._db() as db:
            try:
                db.execute("INSERT INTO courses VALUES (?, ?, ?)", (c.course_code, c.model_dump_json(), now))
            except sqlite3.IntegrityError:
                raise Conflict(f"{c.course_code} already exists") from None
        return now

    def update(self, code: str, c: Course) -> str:
        """Replace course `code`. A changed course_code renames it."""
        now = self._now()
        with self._db() as db:
            if not db.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone():
                raise NotFound(code)
            if c.course_code != code and db.execute(
                    "SELECT 1 FROM courses WHERE code = ?", (c.course_code,)).fetchone():
                raise Conflict(f"{c.course_code} already exists")
            db.execute("UPDATE courses SET code = ?, data = ?, updated_at = ? WHERE code = ?",
                       (c.course_code, c.model_dump_json(), now, code))
        return now

    def delete(self, code: str) -> None:
        with self._db() as db:
            if db.execute("DELETE FROM courses WHERE code = ?", (code,)).rowcount == 0:
                raise NotFound(code)

    def import_dir(self, folder: Path, *, replace: bool = False) -> list[str]:
        """Load every *.json course in `folder`. Existing codes are skipped unless replace."""
        done = []
        for f in sorted(Path(folder).glob("*.json")):
            c = Course.model_validate_json(f.read_text(encoding="utf-8"))
            try:
                self.create(c)
            except Conflict:
                if not replace:
                    continue
                self.update(c.course_code, c)
            done.append(c.course_code)
        return done

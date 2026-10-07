"""HTTP API for the course editor.

    uvicorn acaddoc.api:app --reload        (or: python -m acaddoc serve)

Courses are stored only if they are structurally valid (Pydantic). Business
rules (validate.py) never block saving a draft; they block generating documents.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.background import BackgroundTask

from . import __version__
from .handbook import build_handbook, semester_of
from .render import render_docx
from .schema import Course
from .store import Conflict, NotFound, Store
from .validate import Issue, blocking, validate

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _issues(c: Course) -> list[dict]:
    return [_issue(i) for i in validate(c)]


def _issue(i: Issue) -> dict:
    return {"rule": i.rule, "severity": i.severity, "where": i.where, "message": i.message}


def _summary(c: Course, updated_at: str) -> dict:
    issues = validate(c)
    return {"course_code": c.course_code, "course_title": c.course_title, "kind": c.kind,
            "updated_at": updated_at,
            "errors": sum(i.severity == "error" for i in issues),
            "warnings": sum(i.severity == "warning" for i in issues)}


def _tmp_file(suffix: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(name)


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="AcadDoc", version=__version__)
    app.state.store = store or Store()
    # the Vite dev server runs on another port
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def st() -> Store:
        return app.state.store

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/courses")
    def list_courses():
        return [_summary(c, u) for c, u in st().list()]

    @app.get("/api/courses/{code}")
    def get_course(code: str):
        try:
            c, u = st().get(code)
        except NotFound:
            raise HTTPException(404, f"No course {code}")
        return {"course": c.model_dump(), "updated_at": u, "issues": _issues(c)}

    @app.post("/api/courses", status_code=201)
    def create_course(c: Course):
        try:
            u = st().create(c)
        except Conflict as e:
            raise HTTPException(409, str(e))
        return {"course": c.model_dump(), "updated_at": u, "issues": _issues(c)}

    @app.put("/api/courses/{code}")
    def update_course(code: str, c: Course):
        try:
            u = st().update(code, c)
        except NotFound:
            raise HTTPException(404, f"No course {code}")
        except Conflict as e:
            raise HTTPException(409, str(e))
        return {"course": c.model_dump(), "updated_at": u, "issues": _issues(c)}

    @app.delete("/api/courses/{code}", status_code=204)
    def delete_course(code: str):
        try:
            st().delete(code)
        except NotFound:
            raise HTTPException(404, f"No course {code}")

    @app.post("/api/validate")
    def validate_draft(draft: dict):
        """Check an unsaved draft. Never fails: structural problems come back as data."""
        try:
            c = Course.model_validate(draft)
        except ValidationError as e:
            return {"structure": [{"where": ".".join(map(str, err["loc"])), "message": err["msg"]}
                                  for err in e.errors()], "issues": []}
        return {"structure": [], "issues": _issues(c)}

    @app.get("/api/courses/{code}/docx")
    def course_docx(code: str, force: bool = False):
        try:
            c, _ = st().get(code)
        except NotFound:
            raise HTTPException(404, f"No course {code}")
        errs = blocking(validate(c))
        if errs and not force:
            return JSONResponse({"detail": "Course has blocking errors", "issues": [_issue(i) for i in errs]},
                                status_code=422)
        out = _tmp_file(".docx")
        render_docx(c, out, allow_errors=True)
        return FileResponse(out, media_type=DOCX, filename=f"{c.course_code}.docx",
                            background=BackgroundTask(out.unlink))

    @app.get("/api/programmes")
    def programmes():
        found = sorted({p for c, _ in st().list() for o in c.offerings for p in o.programmes})
        return found

    @app.get("/api/handbook")
    def handbook(programme: str, year: str = Query(..., min_length=4), include_invalid: bool = False):
        courses = [c for c, _ in st().list()]
        if not any(semester_of(c, programme) for c in courses):
            raise HTTPException(404, f"No courses for programme {programme}")
        out = _tmp_file(".docx")
        res = build_handbook(courses, programme, year, out, include_invalid=include_invalid)
        excluded = ",".join(res.excluded)
        return FileResponse(out, media_type=DOCX, filename=f"Handbook_{programme}_{year}.docx",
                            headers={"X-Excluded-Courses": excluded,
                                     "Access-Control-Expose-Headers": "X-Excluded-Courses"},
                            background=BackgroundTask(out.unlink))

    if FRONTEND.is_dir():   # production build of the editor, served from the same address
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


app = create_app()

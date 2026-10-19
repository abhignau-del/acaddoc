"""HTTP API for the course editor.

    python -m acaddoc serve        (or: uvicorn acaddoc.api:app)

Everything except /api/health and /api/auth/* needs a signed-in user. The first
visit to an empty installation creates the administrator account.

Courses are stored only if they are structurally valid (Pydantic). Business
rules (validate.py) never block saving a draft; they block submitting it and
generating documents. workflow.py decides who may do what.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.background import BackgroundTask

from . import __version__, auth, notify, workflow
from .auth import User
from .handbook import build_handbook, semester_of
from .outcomes import LOCF_OUTCOMES, LOCF_SOURCE, Framework, course_level, framework, mapping_programme, suggest_bloom
from .render import render_docx
from .schema import Course, ProgrammeRecord
from .store import Conflict, NotFound, Record, Store
from .validate import Issue, blocking, validate

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "dist"
COOKIE = "acaddoc_session"


# --- request bodies -------------------------------------------------------------------

class SetupBody(BaseModel):
    username: str
    display_name: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


class NewUserBody(BaseModel):
    username: str
    display_name: str
    password: str
    role: str
    department: str = ""
    email: str = ""


class ProfileBody(BaseModel):
    email: str


class UserPatch(BaseModel):
    display_name: str | None = None
    role: str | None = None
    department: str | None = None
    disabled: bool | None = None
    password: str | None = None
    email: str | None = None


class ActionBody(BaseModel):
    comment: str = ""


class MetaPatch(BaseModel):
    department: str | None = None
    owner_id: str | None = None


# --- helpers ----------------------------------------------------------------------------

def _issue(i: Issue) -> dict:
    return {"rule": i.rule, "severity": i.severity, "where": i.where, "message": i.message}


def _meta(r: Record) -> dict:
    m = r.meta
    return {"department": m.department, "owner_id": m.owner_id, "owner_name": r.owner_name,
            "status": m.status, "status_label": workflow.LABELS[m.status],
            "version": m.version, "approved_version": m.approved_version}


def _summary(r: Record, u: User, fw: Framework) -> dict:
    issues = validate(r.course, fw.outcomes)
    return {"course_code": r.course.course_code, "course_title": r.course.course_title, "kind": r.course.kind,
            "updated_at": r.updated_at, **_meta(r),
            "errors": sum(i.severity == "error" for i in issues),
            "warnings": sum(i.severity == "warning" for i in issues),
            "awaiting_me": workflow.why_not(u, "hod_approve", r.meta) is None
                           or workflow.why_not(u, "approve", r.meta) is None}


def _full(r: Record, u: User, fw: Framework) -> dict:
    return {"course": r.course.model_dump(), "updated_at": r.updated_at, **_meta(r),
            "issues": [_issue(i) for i in validate(r.course, fw.outcomes)],
            "can": workflow.permissions(u, r.meta),
            "framework": fw.to_dict(),
            "bloom_suggestions": [suggest_bloom(o.text) for o in r.course.outcomes]}


def _tmp_file(suffix: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(name)


def _docx_response(c: Course, filename: str, fw: Framework | None) -> FileResponse:
    out = _tmp_file(".docx")
    render_docx(c, out, allow_errors=True, framework=fw)
    return FileResponse(out, media_type=DOCX, filename=filename, background=BackgroundTask(out.unlink))


def _bad(e: Exception) -> HTTPException:
    return HTTPException(400, str(e))


_FROM_ENV = object()


def create_app(store: Store | None = None, *, secure_cookies: bool | None = None,
               mailer: "notify.Mailer | None | object" = _FROM_ENV, public_url: str | None = None) -> FastAPI:
    app = FastAPI(title="AcadDoc", version=__version__)
    app.state.store = store or Store()
    app.state.mailer = notify.SmtpMailer.from_env() if mailer is _FROM_ENV else mailer
    app.state.public_url = os.environ.get("ACADDOC_PUBLIC_URL", "") if public_url is None else public_url
    if secure_cookies is None:
        secure_cookies = os.environ.get("ACADDOC_SECURE_COOKIES") == "1"
    throttle = auth.LoginThrottle()

    def st() -> Store:
        return app.state.store

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """Refuse state-changing requests sent from another site (cookie-based sign-in needs this)."""
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
        return await call_next(request)

    def current_user(request: Request) -> User:
        token = request.cookies.get(COOKIE)
        u = st().session_user(token) if token else None
        if not u:
            raise HTTPException(401, "Please sign in")
        return u

    def admin_user(u: User = Depends(current_user)) -> User:
        if not u.is_admin:
            raise HTTPException(403, "Only an administrator can do this")
        return u

    def record(code: str) -> Record:
        try:
            return st().get(code)
        except NotFound:
            raise HTTPException(404, f"No course {code}")

    def fw_of(programme: str) -> Framework:
        """A programme's outcomes: its own record, else the UGC LOCF graduate attributes."""
        return framework(programme, st().programme_record(programme) if programme else None)

    def fw_course(c: Course) -> Framework:
        return fw_of(mapping_programme(c))

    def can_edit_programme(u: User, existing: ProgrammeRecord | None) -> bool:
        if u.disabled:
            return False
        if u.is_admin:
            return True
        return u.role == "hod" and bool(u.department) and (existing is None or existing.department == u.department)

    def require(u: User, action: str, r: Record) -> None:
        reason = workflow.why_not(u, action, r.meta)
        if reason:
            raise HTTPException(403, reason[0].upper() + reason[1:])

    def sign_in(response: Response, u: User) -> dict:
        response.set_cookie(COOKIE, st().new_session(u.id), httponly=True, samesite="lax", secure=secure_cookies,
                            max_age=int(auth.SESSION_DAYS * 86400), path="/")
        return {"user": u.public()}

    # --- accounts -------------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/auth/state")
    def auth_state(request: Request):
        token = request.cookies.get(COOKIE)
        u = st().session_user(token) if token else None
        return {"needs_setup": st().user_count() == 0, "user": u.public() if u else None, "roles": auth.ROLES}

    @app.post("/api/auth/setup")
    def setup(body: SetupBody, response: Response):
        if st().user_count() > 0:
            raise HTTPException(409, "This installation already has accounts")
        try:
            u = st().create_user(body.username, body.display_name, body.password, "admin")
        except (ValueError, Conflict) as e:
            raise _bad(e)
        return sign_in(response, u)

    @app.post("/api/auth/login")
    def login(body: LoginBody, request: Request, response: Response):
        key = f"{body.username.strip().lower()}|{request.client.host if request.client else ''}"
        wait = throttle.wait_s(key)
        if wait:
            raise HTTPException(429, f"Too many attempts. Try again in {int(wait) + 1} seconds.")
        found = st().credentials(body.username)
        if not found:
            auth.burn_time()
        if not found or not auth.verify_password(body.password, found[1]) or found[0].disabled:
            throttle.failed(key)
            raise HTTPException(401, "Wrong username or password")
        throttle.succeeded(key)
        return sign_in(response, found[0])

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE)
        if token:
            st().end_session(token)
        response.delete_cookie(COOKIE, path="/")

    @app.post("/api/auth/password", status_code=204)
    def change_password(body: PasswordBody, u: User = Depends(current_user)):
        _, stored = st().credentials(u.username)
        if not auth.verify_password(body.current_password, stored):
            raise HTTPException(400, "The current password is wrong")
        try:
            st().update_user(u.id, password=body.new_password)   # also signs out every session
        except ValueError as e:
            raise _bad(e)

    @app.patch("/api/auth/me")
    def update_profile(body: ProfileBody, u: User = Depends(current_user)):
        try:
            return {"user": st().update_user(u.id, email=body.email).public()}
        except ValueError as e:
            raise _bad(e)

    @app.get("/api/users")
    def list_users(_: User = Depends(current_user)):
        return [x.public() for x in st().users()]

    @app.post("/api/users", status_code=201)
    def add_user(body: NewUserBody, _: User = Depends(admin_user)):
        try:
            return st().create_user(body.username, body.display_name, body.password, body.role,
                                    body.department, body.email).public()
        except Conflict as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise _bad(e)

    @app.patch("/api/users/{uid}")
    def edit_user(uid: str, body: UserPatch, me: User = Depends(admin_user)):
        try:
            target = st().user(uid)
        except NotFound:
            raise HTTPException(404, "No such user")
        losing_admin = target.is_admin and not target.disabled and (
            (body.role is not None and body.role != "admin") or body.disabled)
        if losing_admin and st().active_admins() <= 1:
            raise HTTPException(409, "There must always be at least one active administrator")
        try:
            return st().update_user(uid, **body.model_dump(exclude_none=True)).public()
        except ValueError as e:
            raise _bad(e)

    # --- courses -------------------------------------------------------------------------

    @app.get("/api/courses")
    def list_courses(u: User = Depends(current_user)):
        cache: dict[str, Framework] = {}
        out = []
        for r in st().list():
            code = mapping_programme(r.course)
            if code not in cache:
                cache[code] = fw_of(code)
            out.append(_summary(r, u, cache[code]))
        return out

    @app.get("/api/courses/{code}")
    def get_course(code: str, u: User = Depends(current_user)):
        r = record(code)
        return _full(r, u, fw_course(r.course))

    @app.post("/api/courses", status_code=201)
    def create_course(c: Course, u: User = Depends(current_user)):
        try:
            return _full(st().create(c, owner=u), u, fw_course(c))
        except Conflict as e:
            raise HTTPException(409, str(e))

    @app.put("/api/courses/{code}")
    def update_course(code: str, c: Course, u: User = Depends(current_user)):
        require(u, "edit", record(code))
        try:
            return _full(st().update(code, c, by=u), u, fw_course(c))
        except Conflict as e:
            raise HTTPException(409, str(e))

    @app.patch("/api/courses/{code}/meta")
    def update_meta(code: str, body: MetaPatch, u: User = Depends(admin_user)):
        record(code)
        try:
            r = st().set_meta(code, department=body.department, owner_id=body.owner_id, by=u)
            return _full(r, u, fw_course(r.course))
        except NotFound:
            raise HTTPException(404, "No such user")

    @app.delete("/api/courses/{code}", status_code=204)
    def delete_course(code: str, u: User = Depends(current_user)):
        require(u, "delete", record(code))
        st().delete(code)

    @app.post("/api/courses/{code}/actions/{action}")
    def act(code: str, action: str, body: ActionBody, background: BackgroundTasks,
            u: User = Depends(current_user)):
        if action not in workflow.ACTIONS:
            raise HTTPException(404, f"No action {action}")
        r = record(code)
        require(u, action, r)
        comment = body.comment.strip()
        if action in workflow.NEEDS_COMMENT and not comment:
            raise HTTPException(400, "Say what needs to change")
        if action == "submit":
            errs = blocking(validate(r.course, fw_course(r.course).outcomes))
            if errs:
                return JSONResponse({"detail": "Fix the errors before submitting",
                                     "issues": [_issue(i) for i in errs]}, status_code=422)
        try:
            r = st().transition(code, action, expect=r.meta.status, to=workflow.next_status(action),
                                by=u, comment=comment)
        except Conflict as e:
            raise HTTPException(409, str(e))
        ids = notify.queue(st(), app.state.mailer, action, r, u, comment, app.state.public_url)
        if ids:   # sent after the response, so mail problems never hold up the workflow
            background.add_task(notify.deliver, st(), app.state.mailer, ids)
        return _full(r, u, fw_course(r.course))

    @app.get("/api/courses/{code}/history")
    def history(code: str, _: User = Depends(current_user)):
        record(code)
        return {"events": st().history(code), "versions": st().versions(code)}

    @app.post("/api/validate")
    def validate_draft(draft: dict, _: User = Depends(current_user)):
        """Check an unsaved draft. Never fails: structural problems come back as data."""
        try:
            c = Course.model_validate(draft)
        except ValidationError as e:
            return {"structure": [{"where": ".".join(map(str, err["loc"])), "message": err["msg"]}
                                  for err in e.errors()], "issues": []}
        fw = fw_course(c)
        return {"structure": [], "issues": [_issue(i) for i in validate(c, fw.outcomes)],
                "framework": fw.to_dict(), "bloom_suggestions": [suggest_bloom(o.text) for o in c.outcomes]}

    @app.get("/api/courses/{code}/docx")
    def course_docx(code: str, force: bool = False, _: User = Depends(current_user)):
        r = record(code)
        fw = fw_course(r.course)
        errs = blocking(validate(r.course, fw.outcomes))
        if errs and not force:
            return JSONResponse({"detail": "Course has blocking errors", "issues": [_issue(i) for i in errs]},
                                status_code=422)
        return _docx_response(r.course, f"{code}.docx", fw)

    @app.get("/api/courses/{code}/versions/{n}/docx")
    def version_docx(code: str, n: int, _: User = Depends(current_user)):
        try:
            c = st().version(code, n)
        except NotFound:
            raise HTTPException(404, f"No version {n} of {code}")
        return _docx_response(c, f"{code}_v{n}.docx", fw_course(c))

    # --- email (admin) -----------------------------------------------------------------------

    @app.get("/api/admin/mail")
    def mail_status(_: User = Depends(admin_user)):
        m = app.state.mailer
        settings = m.describe() if hasattr(m, "describe") else {"configured": m is not None}
        return {**settings, "public_url": app.state.public_url, "outbox": st().outbox()}

    @app.post("/api/admin/mail/test")
    def mail_test(me: User = Depends(admin_user)):
        if not me.email:
            raise HTTPException(400, "Add your own email address first (Account)")
        if app.state.mailer is None:
            raise HTTPException(409, "Email is not configured on the server (see ACADDOC_SMTP_* settings)")
        mid = st().queue_mail(me.email, "[AcadDoc] Test email",
                              f"Dear {me.display_name},\n\nEmail from AcadDoc works.\n")
        notify.deliver(st(), app.state.mailer, [mid])   # now, so the result can be shown
        return st().mail(mid)

    @app.post("/api/admin/mail/{mid}/retry")
    def mail_retry(mid: int, _: User = Depends(admin_user)):
        if app.state.mailer is None:
            raise HTTPException(409, "Email is not configured on the server")
        try:
            row = st().mail(mid)
        except NotFound:
            raise HTTPException(404, "No such message")
        if row["status"] == "sent":
            raise HTTPException(409, "Already sent")
        notify.deliver(st(), app.state.mailer, [mid])
        return st().mail(mid)

    @app.get("/api/programmes")
    def programmes(_: User = Depends(current_user)):
        return sorted({p for r in st().list() for o in r.course.offerings for p in o.programmes})

    # --- programme outcomes ---------------------------------------------------------------

    @app.get("/api/frameworks/locf")
    def locf(_: User = Depends(current_user)):
        return {"source_label": LOCF_SOURCE, "outcomes": [o.model_dump() for o in LOCF_OUTCOMES]}

    @app.get("/api/programme-outcomes")
    def list_programme_outcomes(u: User = Depends(current_user)):
        records = {rec.code: (rec, at, by) for rec, at, by in st().programme_records()}
        courses = st().list()
        offered = {p for r in courses for o in r.course.offerings for p in o.programmes}
        mapped: dict[str, int] = {}
        for r in courses:
            code = mapping_programme(r.course)
            mapped[code] = mapped.get(code, 0) + 1
        out = []
        for code in sorted(offered | set(records)):
            rec, at, by = records.get(code, (None, "", ""))
            out.append({"code": code, "name": rec.name if rec else "", "department": rec.department if rec else "",
                        "own": bool(rec and rec.outcomes), "outcomes": len(rec.outcomes) if rec else 0,
                        "updated_at": at, "updated_by": by, "courses": mapped.get(code, 0),
                        "can_edit": can_edit_programme(u, rec)})
        return out

    @app.get("/api/programme-outcomes/{code}")
    def get_programme_outcomes(code: str, u: User = Depends(current_user)):
        rec = st().programme_record(code)
        fw = fw_of(code)
        rows = []
        for r in st().list():
            if mapping_programme(r.course) != code:
                continue
            c = r.course
            rows.append({"course_code": c.course_code, "course_title": c.course_title,
                         "status_label": workflow.LABELS[r.meta.status],
                         "mapped": any(o.po for o in c.outcomes),
                         "levels": {pc: course_level(c, pc) for pc in fw.codes if course_level(c, pc)}})
        gaps = [pc for pc in fw.codes if not any(pc in row["levels"] for row in rows)]
        return {"code": code, "record": rec.model_dump() if rec else None, "framework": fw.to_dict(),
                "can_edit": can_edit_programme(u, rec), "courses": rows, "gaps": gaps}

    @app.put("/api/programme-outcomes/{code}")
    def save_programme_outcomes(code: str, body: ProgrammeRecord, u: User = Depends(current_user)):
        existing = st().programme_record(code)
        if body.code != code:
            raise HTTPException(400, "The programme code cannot be changed here")
        if not can_edit_programme(u, existing):
            raise HTTPException(403, "Only an administrator or the HOD of the programme's department can edit "
                                     "its outcomes")
        if not u.is_admin and body.department != u.department:
            raise HTTPException(403, f"As HOD you can keep this programme in {u.department} only")
        codes = [o.code for o in body.outcomes]
        dup = sorted({c for c in codes if codes.count(c) > 1})
        if dup:
            raise HTTPException(400, f"Outcome codes must be unique: {', '.join(dup)}")
        st().save_programme(body, by=u)
        return get_programme_outcomes(code, u)

    @app.get("/api/handbook")
    def handbook(programme: str, year: str = Query(..., min_length=4), include_unapproved: bool = False,
                 _: User = Depends(current_user)):
        """Approved versions only, unless include_unapproved (then current content, errors and all)."""
        chosen, unapproved = [], []
        for r in st().list():
            if not semester_of(r.course, programme):
                continue
            if r.meta.approved_version is not None and not include_unapproved:
                chosen.append(st().version(r.meta.code, r.meta.approved_version))
            elif include_unapproved:
                chosen.append(r.course)
            else:
                unapproved.append(r.meta.code)
        if not chosen:
            raise HTTPException(404, f"No approved courses for programme {programme}" if unapproved
                                else f"No courses for programme {programme}")
        out = _tmp_file(".docx")
        res = build_handbook(chosen, programme, year, out, include_invalid=include_unapproved, framework_for=fw_of)
        return FileResponse(out, media_type=DOCX, filename=f"Handbook_{programme}_{year}.docx",
                            headers={"X-Excluded-Courses": ",".join(res.excluded),
                                     "X-Unapproved-Courses": ",".join(unapproved),
                                     "Access-Control-Expose-Headers": "X-Excluded-Courses, X-Unapproved-Courses"},
                            background=BackgroundTask(out.unlink))

    if FRONTEND.is_dir():   # production build of the editor, served from the same address
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


app = create_app()

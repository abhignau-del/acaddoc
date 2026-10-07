# AcadDoc

Faculty enter course content once, in a web form. AcadDoc checks it against the
institution's rules and generates the syllabus in the institution's own Word
format, one course at a time or as a whole programme handbook.

**The idea:** content is structured data; the institution's Word template decides
how it looks; documents are generated, never hand-formatted. A hundred courses
come out looking identical because no one formats them by hand.

## What works today

- **Web editor** for theory courses (modules) and laboratory courses (exercises with
  sub-tasks and tables). Outcome, module and list numbering is automatic.
- **Live checks** while typing: errors that block the document (marks don't add up,
  module hours ≠ contact classes, wrong number of outcomes, empty overview …) and
  warnings (two action verbs in one outcome, missing e-resources …).
- **Drafts survive** a closed tab or a crash: unsaved work is kept in the browser and
  offered back when the course is reopened.
- **DOCX per course**, through a Word template (`backend/templates/course_content.docx`).
- **Programme handbook**: cover, programme structure, contents with page numbers,
  then every course in semester order. Courses with errors are left out and named.
- **Sign-in and roles.** Faculty write courses; the HOD of the course's department
  reviews them; the dean gives final approval; administrators manage accounts and
  never approve. Nobody reviews a course they own.
- **Approval workflow:** Draft → Awaiting HOD → Awaiting dean → Approved, with
  "send back for revision" (a note is required) at either review stage. Courses
  cannot be edited while in review, and cannot be submitted while rules fail.
- **Versions and audit trail.** Each submission freezes a numbered version that can be
  downloaded later. An approved version is never changed: "Start a new version" opens
  a draft while the approved one stays in force. Every step is logged with who, when
  and why.
- **Handbooks use approved versions only** (a preview with current drafts is available).
- **Email notifications.** The HOD hears when a course is submitted, the dean when the
  HOD approves, and the author when it is sent back (with the note) or approved. Each
  email links straight to the course. Everything sent is logged; failures can be retried.
- Command line for the same operations, and a test suite (backend and frontend).

Not yet: importing existing Word files, PDF from the web app (the command line can
make PDFs on a machine with Word or LibreOffice), single sign-on.

## Run it

Needs Python 3.11+ and Node 20+.

```
cd backend
pip install -e ".[dev]"
cd ../frontend
npm install
npm run build
cd ..
python -m acaddoc serve --seed
```

Open http://127.0.0.1:8000. The first visit creates the administrator account; the
administrator then adds faculty, HODs and the dean under **Users**. `--seed` loads four
fictional sample courses into an empty database (`backend/acaddoc.db`; set `ACADDOC_DB`
to put it elsewhere); they have no owner until the administrator assigns one.

An account can also be created from the command line:
`python -m acaddoc user add jdoe --role faculty --display-name "J. Doe" --department CSE`.

When serving over HTTPS, set `ACADDOC_SECURE_COOKIES=1`.

### Email

Notifications are sent through your institution's mail server. Set these before
starting the server, then use **Email → Send me a test email** to check:

| Setting | Example | |
|---|---|---|
| `ACADDOC_SMTP_HOST` | `smtp.office365.com`, `smtp.gmail.com` | required to send |
| `ACADDOC_SMTP_PORT` | `587` | default 587 (465 for `ssl`) |
| `ACADDOC_SMTP_SECURITY` | `starttls`, `ssl` or `none` | default `starttls` |
| `ACADDOC_SMTP_USER` / `ACADDOC_SMTP_PASSWORD` | the sending account | Gmail needs an app password |
| `ACADDOC_MAIL_FROM` | `acaddoc@college.edu` | defaults to the SMTP user |
| `ACADDOC_PUBLIC_URL` | `https://acaddoc.college.edu` | for links in emails |

Without `ACADDOC_SMTP_HOST`, notifications are still recorded in the Email log but not
sent. People set their own address under **Account**; administrators can set it in
**Users**. Leaving it blank opts out.

For frontend development, run `python -m acaddoc serve` and, in `frontend/`,
`npm run dev` (http://localhost:5173, API calls are proxied).

### Command line

```
python -m acaddoc validate backend/samples
python -m acaddoc render   backend/samples --out out           # add --pdf for PDFs
python -m acaddoc handbook backend/samples --programme CSE --year 2026-27 --out out
python -m acaddoc import   backend/samples                      # JSON files into the database
```

### Tests

```
cd backend && python -m pytest -q
cd frontend && npm test
```

## Use your institution's format

The template is an ordinary Word file containing tags such as `{{ course_title }}`.
Fonts, colours, spacing, the letterhead and the header table all live there.
`backend/tools/make_template.py` builds the sample one and accepts a letterhead image:

```
python backend/tools/make_template.py --banner letterhead.png --out my_template.docx
set ACADDOC_TEMPLATE=C:\path\to\my_template.docx
```

Rules (number of modules, outcomes, objectives, course-code pattern) are in
`RULES` at the top of `backend/src/acaddoc/validate.py`.

## Layout

| Path | What it is |
|---|---|
| `backend/src/acaddoc/schema.py` | The course record. The single source of truth. |
| `backend/src/acaddoc/validate.py` | Institutional rules. |
| `backend/src/acaddoc/render.py` | Course → DOCX through the template. Decides the text, never the look. |
| `backend/src/acaddoc/handbook.py` | Programme handbook. |
| `backend/src/acaddoc/workflow.py` | Who may do what, in which state. |
| `backend/src/acaddoc/auth.py` | Password hashing (scrypt), sign-in tokens, login throttling. |
| `backend/src/acaddoc/notify.py` | Who is emailed about what; SMTP sending. |
| `backend/src/acaddoc/store.py` | SQLite: courses, frozen versions, audit trail, users, sessions. |
| `backend/src/acaddoc/api.py` | FastAPI app; also serves the built editor. |
| `backend/samples/` | Fictional sample courses (`tools/make_samples.py`). |
| `frontend/src/` | React + TypeScript editor. `courseops.ts` holds the tested logic. |

## Data policy

Only fictional data is committed. Real syllabi, letterheads and generated documents
belong in the git-ignored `private-data/` folder.

## Licence

MIT. See [LICENSE](LICENSE).

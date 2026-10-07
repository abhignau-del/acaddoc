# AcadDoc

Faculty enter course content once, in a web form. AcadDoc checks it against the
institution's rules and generates the syllabus in the institution's own Word
format, one course at a time or as a whole programme handbook.

**The idea:** content is structured data; the institution's Word template decides
how it looks; documents are generated, never hand-formatted. A hundred courses
come out looking identical because no one formats them by hand.

## What works today (v0.1.0)

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
- Command line for the same operations, and a test suite (backend and frontend).

Not yet: login and roles, approval workflow, version history, importing existing
Word files, PDF from the web app (the command line can make PDFs on a machine with
Word or LibreOffice).

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

Open http://127.0.0.1:8000. `--seed` loads four fictional sample courses into an
empty database (`backend/acaddoc.db`; set `ACADDOC_DB` to put it elsewhere).

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
| `backend/src/acaddoc/store.py` | SQLite storage (one validated JSON record per course). |
| `backend/src/acaddoc/api.py` | FastAPI app; also serves the built editor. |
| `backend/samples/` | Fictional sample courses (`tools/make_samples.py`). |
| `frontend/src/` | React + TypeScript editor. `courseops.ts` holds the tested logic. |

## Data policy

Only fictional data is committed. Real syllabi, letterheads and generated documents
belong in the git-ignored `private-data/` folder.

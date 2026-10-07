"""Command line:

    python -m acaddoc validate  samples
    python -m acaddoc render    samples/MTH101.json --pdf
    python -m acaddoc handbook  samples --programme CSE --year 2026-27 --pdf
    python -m acaddoc import    samples            # load JSON courses into the database
    python -m acaddoc serve     [--seed]           # web editor at http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .handbook import build_handbook
from .render import InvalidCourse, render_docx, to_pdf
from .schema import Course
from .validate import blocking, validate


def load(path: Path) -> list[Course]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    return [Course.model_validate_json(f.read_text(encoding="utf-8")) for f in files]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="acaddoc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("path", type=Path)
    r = sub.add_parser("render"); r.add_argument("path", type=Path)
    r.add_argument("--out", type=Path, default=Path("out")); r.add_argument("--pdf", action="store_true")
    r.add_argument("--force", action="store_true", help="render even with blocking errors")
    h = sub.add_parser("handbook"); h.add_argument("path", type=Path)
    h.add_argument("--programme", required=True); h.add_argument("--year", required=True)
    h.add_argument("--out", type=Path, default=Path("out")); h.add_argument("--pdf", action="store_true")
    h.add_argument("--include-invalid", action="store_true")
    i = sub.add_parser("import"); i.add_argument("path", type=Path)
    i.add_argument("--replace", action="store_true", help="overwrite courses that already exist")
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8000)
    s.add_argument("--seed", action="store_true", help="load the sample courses if the database is empty")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        from .api import app
        if a.seed and not app.state.store.list():
            app.state.store.import_dir(Path(__file__).resolve().parents[2] / "samples")
        uvicorn.run(app, host="127.0.0.1", port=a.port)
        return 0
    if a.cmd == "import":
        from .store import Store
        print("imported:", ", ".join(Store().import_dir(a.path, replace=a.replace)) or "nothing new")
        return 0

    courses = load(a.path)
    if a.cmd == "validate":
        bad = 0
        for c in courses:
            issues = validate(c)
            print(f"{c.course_code}  {c.course_title}  [{'OK' if not blocking(issues) else 'BLOCKED'}]")
            for i in issues:
                print("   ", i)
            bad += bool(blocking(issues))
        return 1 if bad else 0

    if a.cmd == "render":
        rc = 0
        for c in courses:
            dest = a.out / f"{c.course_code}.docx"
            try:
                render_docx(c, dest, allow_errors=a.force)
            except InvalidCourse as e:
                print(e); rc = 1; continue
            print("wrote", dest)
            if a.pdf:
                print("wrote", to_pdf(dest))
        return rc

    dest = a.out / f"Handbook_{a.programme.replace(' ', '_')}_{a.year}.docx"
    res = build_handbook(courses, a.programme, a.year, dest, include_invalid=a.include_invalid)
    print(f"wrote {dest}: {len(res.included)} course(s)")
    for code, errs in res.excluded.items():
        print(f"  EXCLUDED {code}:")
        for e in errs:
            print("     ", e)
    if a.pdf:
        print("wrote", to_pdf(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())

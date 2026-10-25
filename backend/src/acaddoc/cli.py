"""Command line:

    python -m acaddoc validate  samples
    python -m acaddoc render    samples/MTH101.json --pdf
    python -m acaddoc handbook  samples --programme CSE --year 2026-27 --pdf
    python -m acaddoc pack      samples --programme CSE -o CSE_pack.json   # for Curriculum Intelligence
    (validate/render/handbook/pack take --programmes samples/programmes for programme outcomes)
    python -m acaddoc import    samples            # load JSON courses into the database
    python -m acaddoc serve     [--seed]           # web editor at http://127.0.0.1:8000
    python -m acaddoc user add  NAME --role admin --display-name "A. Admin" [--department CSE]
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


def frameworks(folder: Path | None):
    """programme code -> Framework, from a folder of programme JSON files (LOCF when absent)."""
    from .outcomes import framework
    from .schema import ProgrammeRecord
    recs = {}
    if folder:
        for f in sorted(Path(folder).glob("*.json")):
            rec = ProgrammeRecord.model_validate_json(f.read_text(encoding="utf-8"))
            recs[rec.code] = rec
    return lambda code: framework(code, recs.get(code)) if folder else None


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
    pk = sub.add_parser("pack", help="write a programme pack (outcomes + courses) for other tools")
    pk.add_argument("path", type=Path); pk.add_argument("--programme", required=True)
    pk.add_argument("-o", "--out", type=Path, required=True)
    for sp in (v, r, h, pk):
        sp.add_argument("--programmes", type=Path, help="folder of programme-outcome JSON files")
    i = sub.add_parser("import"); i.add_argument("path", type=Path)
    i.add_argument("--replace", action="store_true", help="overwrite courses that already exist")
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8000)
    s.add_argument("--seed", action="store_true", help="load the sample courses if the database is empty")
    u = sub.add_parser("user"); usub = u.add_subparsers(dest="ucmd", required=True)
    ua = usub.add_parser("add", help="create an account (asks for the password)")
    ua.add_argument("username"); ua.add_argument("--display-name", required=True)
    ua.add_argument("--role", required=True, choices=["admin", "faculty", "hod", "dean"])
    ua.add_argument("--department", default="")
    a = ap.parse_args(argv)

    if a.cmd == "user":
        import getpass

        from .store import Conflict, Store
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Again: "):
            print("The passwords differ."); return 1
        try:
            made = Store().create_user(a.username, a.display_name, pw, a.role, a.department)
        except (ValueError, Conflict) as e:
            print(e); return 1
        print(f"created {made.username} ({made.role})")
        return 0

    if a.cmd == "serve":
        import uvicorn

        from .api import app
        if a.seed and not app.state.store.list():
            samples = Path(__file__).resolve().parents[2] / "samples"
            app.state.store.import_dir(samples)
            app.state.store.import_programmes(samples / "programmes")
        uvicorn.run(app, host="127.0.0.1", port=a.port)
        return 0
    if a.cmd == "import":
        from .store import Store
        print("imported:", ", ".join(Store().import_dir(a.path, replace=a.replace)) or "nothing new")
        return 0

    from .outcomes import mapping_programme
    courses = load(a.path)
    fw_of = frameworks(a.programmes)

    def fw(c):
        return fw_of(mapping_programme(c))

    if a.cmd == "pack":
        import json

        from .outcomes import framework as fw_default
        from .pack import PackItem, build_pack
        from .handbook import semester_of
        items = [PackItem(c) for c in courses if semester_of(c, a.programme)]
        if not items:
            print(f"no courses offered to {a.programme}"); return 1
        pack = build_pack(a.programme, fw_of(a.programme) or fw_default(a.programme, None), items, basis="current")
        a.out.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
        print(f"wrote {a.out}: {len(pack['courses'])} course(s), {len(pack['programme']['outcomes'])} programme outcomes"
              f" ({pack['programme']['source']})")
        for n in pack["notes"]:
            print("  note:", n)
        return 0

    if a.cmd == "validate":
        bad = 0
        for c in courses:
            issues = validate(c, fw(c).outcomes if fw(c) else None)
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
                render_docx(c, dest, allow_errors=a.force, framework=fw(c))
            except InvalidCourse as e:
                print(e); rc = 1; continue
            print("wrote", dest)
            if a.pdf:
                print("wrote", to_pdf(dest))
        return rc

    dest = a.out / f"Handbook_{a.programme.replace(' ', '_')}_{a.year}.docx"
    res = build_handbook(courses, a.programme, a.year, dest, include_invalid=a.include_invalid,
                         framework_for=fw_of if a.programmes else None)
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

"""One-off bootstrap: read clean "Course Content" PDFs in one known layout into course JSON.

This is NOT the product's import feature. It exists so the six sample courses
are not retyped by hand (and so source typos are preserved, not 'fixed').
It only understands this one clean layout.

    python tools/import_pdf.py <pdf> [<pdf> ...]   -> ../private-data/courses/<CODE>.json  (git-ignored)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from acaddoc.schema import Course  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "private-data" / "courses"
LABELS = ("Vocabulary", "Grammar", "Reading", "Writing")
SECTIONS = [
    ("overview", r"I\.\s*COURSE\s+OVERVIEW"),
    ("objectives", r"II\.\s*COURSES?\s+OBJECTIVES"),
    ("outcomes", r"III\.\s*COURSE\s+OUTCOMES"),
    ("content", r"IV\.\s*COURSES?\s+CONTENT"),
    ("text_books", r"V\.\s*TEXT\s*BOOKS"),
    ("reference_books", r"VI\.\s*REFERENCE\s+BOOKS"),
    ("electronic_resources", r"VII\.\s*ELECTRONICS?\s+RESOURCES"),
    ("materials_online", r"VIII\.\s*MATERIALS?\s+ONLINE"),
]


def lines_of(pdf: Path) -> list[str]:
    with pdfplumber.open(pdf) as p:
        text = "\n".join(pg.extract_text() or "" for pg in p.pages)
    keep = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not re.match(r"^\d+\s*\|\s*P\s*age$", ln):
            keep.append(ln)
    return keep


def split_sections(lines):
    idx = {}
    for i, ln in enumerate(lines):
        for name, pat in SECTIONS:
            if name not in idx and re.match(pat, ln, re.I):
                idx[name] = i
    order = sorted(idx.items(), key=lambda kv: kv[1])
    head = lines[: order[0][1]]
    body = {}
    for (name, i), nxt in zip(order, order[1:] + [("end", len(lines))]):
        body[name] = lines[i + 1 : nxt[1]]
        if name == "overview":
            body[name] = lines[i + 1 : nxt[1]]
    return head, body


def num_list(lines, marker=r"(?:\d+|[IVX]+)[.)]?"):
    """Numbered/roman list -> items, joining wrapped lines."""
    items = []
    for ln in lines:
        m = re.match(rf"^({marker})\s+(.*)$", ln)
        if m and (m.group(1).rstrip(".)").isdigit() or re.fullmatch(r"[IVX]+\.?", m.group(1))):
            items.append(m.group(2))
        elif items:
            items[-1] += " " + ln
    return [re.sub(r"\s+", " ", i).strip() for i in items]


def parse_header(head):
    h = {"offerings": []}
    h["course_title"] = head[1]
    i = 2
    while not head[i].startswith("Course Code"):
        m = re.match(r"^([IVX]+)\s+Semester:\s*(.*)$", head[i])
        if m:
            progs = [p.strip() for p in re.split(r"\s*[/|ǀ]\s*", m.group(2)) if p.strip()]
            h["offerings"].append({"semester": m.group(1), "programmes": progs})
        i += 1
    code, cat = head[i + 2].split(None, 1)
    nums = head[i + 3].split()
    d = lambda x: 0 if x in ("-", "Nil") else int(x)
    L, T, P, C, cia, see, tot = (d(x) for x in nums)
    cc = re.search(
        r"Contact Classes:\s*(\w+)\s+Tutorial Classes:\s*(\w+)\s+Practical Classes:\s*(\w+)\s+Total Classes:\s*(\w+)",
        head[i + 4],
    )
    a, b, c_, t = (d(x) for x in cc.groups())
    h.update(
        course_code=code, category=cat,
        hours=dict(lecture=L, tutorial=T, practical=P, credits=C, contact_classes=a,
                   tutorial_classes=b, practical_classes=c_, total_classes=t),
        marks=dict(cia=cia, see=see, total=tot),
        prerequisite=" ".join(head[i + 5 :]).replace("Prerequisite:", "").strip(),
    )
    return h


def parse_outcomes(lines):
    out = []
    for ln in lines:
        m = re.match(r"^CO\s*(\d+):?\s+(.*)$", ln)
        if m:
            out.append({"code": f"CO{m.group(1)}", "text": m.group(2)})
        elif out and not ln.startswith(("At the end", "After successful")):
            out[-1]["text"] += " " + ln
    return [{**o, "text": re.sub(r"\s+", " ", o["text"]).strip()} for o in out]


def parse_modules(lines):
    mods, cur = [], None
    for ln in lines:
        m = re.match(r"^MODULE\s*[–-]\s*[IVX]+\s*:\s*(.*?)\s*(?:\((\d+)\))?$", ln)
        if m:
            cur = {"title": m.group(1).strip(), "hours": int(m.group(2)) if m.group(2) else None, "parts": []}
            mods.append(cur)
            continue
        lab = re.match(rf"^({'|'.join(LABELS)})\s*:\s*(.*)$", ln)
        if lab:
            cur["parts"].append({"label": lab.group(1), "text": lab.group(2)})
        elif not cur["parts"] or cur["parts"][-1].get("_closed"):
            cur["parts"].append({"text": ln})
        else:
            cur["parts"][-1]["text"] += " " + ln
        if ln.endswith(".") and not lab and "label" not in cur["parts"][-1]:
            cur["parts"][-1]["_closed"] = True
    for m in mods:
        for p in m["parts"]:
            p.pop("_closed", None)
            p["text"] = re.sub(r"\s+", " ", p["text"]).strip()
    return mods


ROW = re.compile(r"^(.+?)\s+(Number|Integer|Date|Varchar2\(.*\))$")


def parse_exercises(lines):
    exs, ex, item, sub = [], None, None, None
    for ln in lines:
        m = re.match(r"^EXERCISE\s*[–-]\s*\d+\s*:\s*(.*)$", ln)
        if m:
            ex = {"title": m.group(1).strip(), "items": []}
            exs.append(ex); item = sub = None
            continue
        if ln == "Name Type":
            if item is None:   # exercise 1: the PDF text layer puts the table before item 1
                item = {"text": "Create a table called Employee with the following structure",
                        "subitems": []}
                ex["items"].append(item)
            item["table"] = {"header": ["Name", "Type"], "rows": []}
            continue
        if item and item.get("table") is not None and "Create a table called Empl" in ln:
            # overprinted text in the source PDF swallowed the 'Job' row
            item["table"]["rows"].append(["Job", "Varchar2(20)"])
            continue
        if item and item.get("table") is not None and not item.get("_tdone") and ROW.match(ln) \
                and not re.match(r"^\d+\.", ln):
            item["table"]["rows"].append(list(ROW.match(ln).groups()))
            continue
        if item and item.get("table") is not None:
            item["_tdone"] = True
        mi = re.match(r"^(\d+)\.\s+(.*)$", ln)
        ms = re.match(r"^([a-z])\.\s+(.*)$", ln)
        if mi:
            lead = re.match(r"^([a-z])\.\s+(.*)$", mi.group(2))
            if lead:   # "1. a. Create a user ..." -> numbered heading with no text, first sub-item
                item = {"text": "", "subitems": [lead.group(2)]}; sub = True
            else:
                item = {"text": mi.group(2), "subitems": []}; sub = None
            ex["items"].append(item)
        elif ms and item is not None:
            item["subitems"].append(ms.group(2)); sub = True
        elif item is not None:
            if sub:
                item["subitems"][-1] += " " + ln
            else:
                item["text"] += " " + ln
    for ex in exs:
        for it in ex["items"]:
            it.pop("_tdone", None)
            it["text"] = re.sub(r"\s+", " ", it["text"]).strip()
            it["subitems"] = [re.sub(r"\s+", " ", s).strip() for s in it["subitems"]]
            if it.get("table") is None:
                it.pop("table", None)
    return exs


def build(pdf: Path) -> dict:
    head, body = split_sections(lines_of(pdf))
    c = parse_header(head)
    c["overview"] = re.sub(r"\s+", " ", " ".join(body["overview"]))
    c["objectives"] = num_list([l for l in body["objectives"] if not l.startswith(("The students", "After "))])
    c["outcomes"] = parse_outcomes(body["outcomes"])
    c["kind"] = "laboratory" if any(l.startswith("EXERCISE") for l in body["content"]) else "theory"
    c["modules"] = parse_modules(body["content"]) if c["kind"] == "theory" else []
    c["exercises"] = parse_exercises(body["content"]) if c["kind"] == "laboratory" else []
    for k in ("text_books", "reference_books", "electronic_resources", "materials_online"):
        c[k] = num_list(body.get(k, []))
    return c


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        data = build(Path(arg))
        Course.model_validate(data)   # structure only; the business rules run later
        dest = OUT / f"{data['course_code']}.json"
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote", dest.name, data["kind"], len(data["modules"]) or len(data["exercises"]))

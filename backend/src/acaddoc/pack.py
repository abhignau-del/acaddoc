"""Programme pack: one JSON file with a programme's outcomes and every course offered to it.

Made for other tools (Curriculum Intelligence reads it) and as a plain backup. Format:

    {"format": "acaddoc-programme-pack", "version": 1, "generated_at": ..., "generator": "AcadDoc x.y.z",
     "basis": "approved" | "current",
     "programme": {"code", "name", "department", "source": "programme" | "locf", "outcomes": [{code, title, text}]},
     "courses": [{"status", "version", "semester", "mapped_to", "course": {AcadDoc course}}],
     "left_out": [{"course_code", "course_title", "reason"}],
     "notes": ["..."]}

A course mapped to another programme's outcomes keeps its Bloom levels but loses its
CO-PO links in the pack: "PO1" means something else in that programme.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import __version__
from .handbook import select
from .outcomes import Framework, mapping_programme
from .schema import Course

FORMAT = "acaddoc-programme-pack"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class PackItem:
    course: Course                  # the content to export (an approved version, or the current draft)
    status: str = "draft"           # workflow status label, e.g. "approved"
    version: int | None = None      # the frozen version exported, None for current content


def build_pack(programme: str, fw: Framework, items: list[PackItem], *, basis: str = "approved",
               left_out: list[tuple[Course, str]] | None = None, department: str = "") -> dict:
    """`items`: the courses to export; `left_out`: (course, reason) for those deliberately not exported."""
    by_code = {it.course.course_code: it for it in items}
    ordered = select([it.course for it in items], programme)         # semester order, as the handbook
    courses, notes = [], []
    for sem, c in ordered:
        it = by_code[c.course_code]
        data = c.model_dump()
        target = mapping_programme(c)
        if target != programme and any(o["po"] for o in data["outcomes"]):
            for o in data["outcomes"]:
                o["po"] = {}
            notes.append(f"{c.course_code} is mapped to the outcomes of {target or 'no programme'}; "
                         "its CO-PO links are left out.")
        courses.append({"status": it.status, "version": it.version, "semester": sem, "mapped_to": target,
                        "course": data})
    return {
        "format": FORMAT, "version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": f"AcadDoc {__version__}",
        "basis": basis,
        "programme": {"code": programme, "name": fw.name, "department": department,
                      "source": fw.source, "outcomes": [o.model_dump() for o in fw.outcomes]},
        "courses": courses,
        "left_out": [{"course_code": c.course_code, "course_title": c.course_title, "reason": why}
                     for c, why in (left_out or [])],
        "notes": notes,
    }

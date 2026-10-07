"""Institutional validation rules.

Rules live in code for now. Once a second institution needs different numbers,
`RULES` below is the one place to move into a YAML file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .schema import Course

# Institutional parameters. Change these, not the checks.
RULES = {
    "course_code_pattern": r"^[A-Z]{2,6}\d{2,4}$",
    "theory_modules": 5,
    "outcomes": 6,
    "objectives": 4,
}

# Bloom action verbs; two of them in one outcome usually means an edit left
# the old verb behind ("Compare Identify suitable ...").
_VERBS = {
    "apply", "analyze", "analyse", "compare", "construct", "define", "describe",
    "determine", "develop", "evaluate", "execute", "explain", "identify",
    "illustrate", "implement", "interpret", "make", "review", "state",
    "utilize", "use", "demonstrate", "design", "create", "find", "gain",
}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str          # "error" blocks generation; "warning" does not
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.rule:22} {self.where}: {self.message}"


def validate(c: Course) -> list[Issue]:
    out: list[Issue] = []

    def err(rule, where, msg):
        out.append(Issue(rule, "error", where, msg))

    def warn(rule, where, msg):
        out.append(Issue(rule, "warning", where, msg))

    h = c.hours
    if not re.match(RULES["course_code_pattern"], c.course_code):
        err("COURSE_CODE_FORMAT", "course_code", f"'{c.course_code}' does not match the institutional pattern")

    if not c.offerings:
        err("OFFERING_REQUIRED", "offerings", "say which semester and programme the course is offered to")
    for i, o in enumerate(c.offerings, 1):
        if not o.programmes:
            err("OFFERING_PROGRAMMES", f"offerings[{i}]", f"{o.semester} Semester lists no programmes")
    if not c.overview.strip():
        err("OVERVIEW_REQUIRED", "overview", "the course overview is empty")

    if c.marks.cia + c.marks.see != c.marks.total:
        err("MARKS_TOTAL", "marks", f"CIA {c.marks.cia} + SEE {c.marks.see} != Total {c.marks.total}")
    if h.contact_classes + h.tutorial_classes + h.practical_classes != h.total_classes:
        err("CLASSES_TOTAL", "hours",
            f"contact {h.contact_classes} + tutorial {h.tutorial_classes} + practical "
            f"{h.practical_classes} != total {h.total_classes}")
    if h.lecture + h.tutorial + h.practical / 2 != h.credits:
        warn("CREDITS_FORMULA", "hours",
             f"L{h.lecture}+T{h.tutorial}+P{h.practical}/2 gives "
             f"{h.lecture + h.tutorial + h.practical / 2:g}, but credits are {h.credits}")

    if len(c.objectives) != RULES["objectives"]:
        warn("OBJECTIVE_COUNT", "objectives", f"{len(c.objectives)} objectives, expected {RULES['objectives']}")
    if len(c.outcomes) != RULES["outcomes"]:
        err("OUTCOME_COUNT", "outcomes", f"{len(c.outcomes)} outcomes, expected {RULES['outcomes']}")
    for i, o in enumerate(c.outcomes, 1):
        if o.code.replace(" ", "") != f"CO{i}":
            err("OUTCOME_NUMBERING", f"outcomes[{i}]", f"expected CO{i}, found {o.code}")
        words = re.findall(r"[A-Za-z]+", o.text)
        extra = [w for prev, w in zip(words, words[1:])
                 if w[0].isupper() and w.lower() in _VERBS and not (prev.lower() == "make" and w.lower() == "use")]
        if extra:
            warn("OUTCOME_TWO_VERBS", f"outcomes[{i}]", f"capitalised verb(s) {extra} mid-sentence; leftover edit?")

    if c.kind == "theory":
        if c.exercises:
            err("KIND_MISMATCH", "exercises", "a theory course must not list exercises")
        if len(c.modules) != RULES["theory_modules"]:
            err("MODULE_COUNT", "modules", f"{len(c.modules)} modules, expected {RULES['theory_modules']}")
        for i, m in enumerate(c.modules, 1):
            if not m.title.strip():
                err("MODULE_TITLE_REQUIRED", f"modules[{i}]", f"module {i} has no title")
            if not any(p.text.strip() for p in m.parts):
                err("MODULE_EMPTY", f"modules[{i}]", f"module {i} has no content")
        hours = [m.hours for m in c.modules]
        if any(x is None for x in hours):
            warn("MODULE_HOURS_MISSING", "modules", "module hours not stated")
        elif sum(hours) != h.contact_classes:
            err("MODULE_HOURS_SUM", "modules",
                f"module hours add up to {sum(hours)}, but the course has {h.contact_classes} contact classes")
    else:
        if c.modules:
            err("KIND_MISMATCH", "modules", "a laboratory course lists exercises, not modules")
        if not c.exercises:
            err("EXERCISES_REQUIRED", "exercises", "no exercises")
        for i, ex in enumerate(c.exercises, 1):
            if not ex.title.strip():
                err("EXERCISE_TITLE_REQUIRED", f"exercises[{i}]", f"exercise {i} has no title")
            if not any(it.text.strip() or it.subitems for it in ex.items):
                err("EXERCISE_EMPTY", f"exercises[{i}]", f"exercise {i} has no tasks")

    if not c.text_books:
        err("TEXT_BOOKS_REQUIRED", "text_books", "at least one text book is required")
    if not c.electronic_resources:
        warn("E_RESOURCES_MISSING", "electronic_resources", "none listed")
    for i, r in enumerate(c.electronic_resources, 1):
        if r.startswith("http"):
            u = urlparse(r.split()[-1])
            if not u.netloc or " " in r.strip():
                warn("URL_MALFORMED", f"electronic_resources[{i}]", r)
    dup = {b for b in c.text_books + c.reference_books if (c.text_books + c.reference_books).count(b) > 1}
    for b in dup:
        warn("REFERENCE_DUPLICATE", "references", b[:60])
    return out


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]

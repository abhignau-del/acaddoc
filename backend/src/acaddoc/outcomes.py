"""Course outcomes against programme outcomes: Bloom levels, CO-PO mapping, frameworks.

No guessing of mappings: faculty decide every CO-PO link. The only suggestion this
module makes is a Bloom level read off an outcome's opening verb, from a fixed
word list, which faculty accept or change.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .schema import BLOOM_LEVELS, Course, ProgrammeOutcome, ProgrammeRecord

BLOOM_LABELS = {b: b.capitalize() for b in BLOOM_LEVELS}
STRENGTH_LABELS = {3: "High", 2: "Moderate", 1: "Low"}

# Revised Bloom's taxonomy action verbs (Anderson & Krathwohl, 2001), one level per verb.
# Same list as Curriculum Intelligence (taxonomies/bloom.yaml); where lists disagree,
# the level most syllabi intend. "understand" stays at its level but says little.
_VERBS: dict[str, list[str]] = {
    "remember": ["define", "list", "state", "recall", "name", "identify", "label", "match", "memorise",
                 "memorize", "recognise", "recognize", "reproduce", "recite", "record", "repeat",
                 "enumerate", "quote", "tabulate", "know"],
    "understand": ["explain", "describe", "discuss", "summarise", "summarize", "interpret", "classify",
                   "illustrate", "paraphrase", "outline", "express", "represent", "translate", "restate",
                   "review", "exemplify", "explore", "comprehend", "understand"],
    "apply": ["apply", "use", "solve", "compute", "calculate", "determine", "find", "demonstrate",
              "implement", "execute", "perform", "carry out", "draw", "sketch", "plot", "graph", "construct",
              "interpolate", "approximate", "estimate", "differentiate", "integrate", "simplify", "transform",
              "convert", "manipulate", "operate", "practise", "practice", "employ", "utilise", "utilize",
              "make use of", "write", "program", "code", "visualise", "visualize", "measure", "work out",
              "handle", "obtain", "evaluate the", "locate", "reduce", "factorise", "factorize", "model"],
    "analyse": ["analyse", "analyze", "compare", "contrast", "distinguish", "examine", "investigate",
                "categorise", "categorize", "deduce", "derive", "relate", "inspect", "test", "discriminate",
                "organise", "organize", "break down", "infer", "characterise", "characterize", "decompose",
                "diagnose"],
    "evaluate": ["evaluate", "prove", "justify", "verify", "assess", "judge", "critique", "criticise",
                 "criticize", "argue", "validate", "check", "appraise", "defend", "conclude", "recommend",
                 "select", "choose", "establish"],
    "create": ["create", "design", "develop", "formulate", "compose", "devise", "propose", "plan", "produce",
               "generate", "invent", "build", "synthesise", "synthesize", "hypothesise", "hypothesize",
               "modify", "adapt", "improve", "extend", "conjecture", "construct a model"],
}
# Longest phrases first, so "make use of" wins over "make" and "evaluate the" over "evaluate".
_PHRASES = sorted(((v, lvl) for lvl, vs in _VERBS.items() for v in vs), key=lambda x: -len(x[0]))
_LEAD_IN = re.compile(r"^(?:(?:students?|learners?)\s+(?:will|should|shall)\s+(?:be\s+able\s+to\s+)?|"
                      r"(?:be\s+)?able\s+to\s+|to\s+)", re.I)


def suggest_bloom(text: str) -> str | None:
    """The Bloom level of the outcome's opening verb, or None if it does not start with a known one."""
    t = _LEAD_IN.sub("", text.strip()).lower()
    for phrase, level in _PHRASES:
        if re.match(rf"{re.escape(phrase)}\b", t):
            return level
    return None


# Graduate attributes of UGC's Learning Outcomes-based Curriculum Framework (LOCF), B.A./B.Sc.
# (Honours) Mathematics, section 3 (pp. 5-6), condensed. The starting point for a programme
# that has not written its own outcomes; the same list Curriculum Intelligence uses.
LOCF_SOURCE = "UGC LOCF graduate attributes (B.A./B.Sc. Honours Mathematics, section 3)"
LOCF_OUTCOMES = [
    ProgrammeOutcome(code="GA1", title="Disciplinary knowledge",
                     text="Comprehensive knowledge of mathematics and understanding of the disciplines in the programme."),
    ProgrammeOutcome(code="GA2", title="Communication skills",
                     text="Communicate mathematical concepts effectively, with examples and geometric visualisation, "
                          "and use mathematics as a precise language."),
    ProgrammeOutcome(code="GA3", title="Critical thinking and analytical reasoning",
                     text="Think critically about mathematical concepts, analyse results and apply them across "
                          "branches of mathematics."),
    ProgrammeOutcome(code="GA4", title="Problem solving",
                     text="Solve problems, including models of growth and decay, linear systems and linear "
                          "programming, and give new solutions using mathematics."),
    ProgrammeOutcome(code="GA5", title="Research-related skills",
                     text="Ask appropriate questions about mathematical concepts and follow advances in the subject."),
    ProgrammeOutcome(code="GA6", title="Information/digital literacy",
                     text="Use appropriate software and programming to solve equations and carry out mathematical "
                          "investigations."),
    ProgrammeOutcome(code="GA7", title="Self-directed learning",
                     text="Work independently and study notions of mathematics in depth."),
    ProgrammeOutcome(code="GA8", title="Moral and ethical awareness/reasoning",
                     text="Recognise unethical behaviour such as fabricating or misrepresenting data, and act "
                          "objectively and truthfully."),
    ProgrammeOutcome(code="GA9", title="Lifelong learning",
                     text="Acquire knowledge and skills through logical reasoning, and keep learning."),
]


@dataclass(frozen=True)
class Framework:
    """The programme outcomes one course's mapping is made against."""
    programme: str                     # programme code, "" if the course is offered to none
    source: str                        # "programme" (its own record) or "locf" (the UGC default)
    outcomes: list[ProgrammeOutcome]
    name: str = ""

    @property
    def codes(self) -> list[str]:
        return [o.code for o in self.outcomes]

    def to_dict(self) -> dict:
        return {"programme": self.programme, "source": self.source, "name": self.name,
                "source_label": "" if self.source == "programme" else LOCF_SOURCE,
                "outcomes": [o.model_dump() for o in self.outcomes]}


def mapping_programme(c: Course) -> str:
    """Whose outcomes the course is mapped to: po_programme, else the first programme offered."""
    if c.po_programme:
        return c.po_programme
    for o in c.offerings:
        if o.programmes:
            return o.programmes[0]
    return ""


def framework(programme: str, record: ProgrammeRecord | None) -> Framework:
    if record is not None and record.outcomes:
        return Framework(programme, "programme", list(record.outcomes), record.name)
    return Framework(programme, "locf", list(LOCF_OUTCOMES), record.name if record else "")


def _code_key(code: str) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", code)
    return (m.group(1), int(m.group(2))) if m else (code, 0)


def columns(c: Course, fw: Framework | None) -> list[str]:
    """Matrix columns: the framework's outcomes in order, then any other code the course uses."""
    used = {p for o in c.outcomes for p in o.po}
    base = fw.codes if fw else []
    return base + sorted(used - set(base), key=_code_key)


def course_level(c: Course, code: str) -> int | None:
    """One course's strength for a programme outcome: the rounded mean of its COs' links (None if none)."""
    vals = [o.po[code] for o in c.outcomes if code in o.po]
    return math.floor(sum(vals) / len(vals) + 0.5) if vals else None


def strength_mark(v: int | None) -> str:
    return str(v) if v else "-"

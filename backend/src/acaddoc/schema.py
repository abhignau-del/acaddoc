"""The structured course record: the single source of truth.

Everything a faculty member enters lives here. Nothing in this module knows
about fonts, margins or Word; that belongs to the template.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemesterOffering(_Model):
    """'III Semester: CSE / IT' -> semester 'III', programmes ['CSE', 'IT']."""
    semester: str
    programmes: list[str]


class Marks(_Model):
    cia: int
    see: int
    total: int


class Hours(_Model):
    """Weekly L-T-P and credits, plus the semester totals printed in the header."""
    lecture: int = 0
    tutorial: int = 0
    practical: int = 0
    credits: int
    contact_classes: int = 0
    tutorial_classes: int = 0
    practical_classes: int = 0
    total_classes: int = 0


class Part(_Model):
    """One paragraph of module text, optionally with a bold label ('Vocabulary')."""
    text: str
    label: Optional[str] = None


class Module(_Model):
    title: str
    hours: Optional[int] = None
    parts: list[Part]


class Table(_Model):
    header: list[str]
    rows: list[list[str]]


class ExerciseItem(_Model):
    text: str
    table: Optional[Table] = None
    subitems: list[str] = Field(default_factory=list)


class Exercise(_Model):
    title: str
    items: list[ExerciseItem]


class Outcome(_Model):
    code: str          # "CO1" (the template prints it as "CO 1")
    text: str


class Course(_Model):
    # the code is the record's key and appears in URLs and file names
    course_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    course_title: str = Field(min_length=1)
    kind: Literal["theory", "laboratory"] = "theory"
    category: str                                   # Foundation / Core / ...
    offerings: list[SemesterOffering]
    hours: Hours
    marks: Marks
    prerequisite: str = ""

    overview: str
    objectives: list[str]
    outcomes: list[Outcome]

    modules: list[Module] = Field(default_factory=list)       # theory
    exercises: list[Exercise] = Field(default_factory=list)   # laboratory

    text_books: list[str]
    reference_books: list[str] = Field(default_factory=list)
    electronic_resources: list[str] = Field(default_factory=list)
    materials_online: list[str] = Field(default_factory=list)

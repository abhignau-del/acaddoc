"""Checks against real syllabi kept in the git-ignored private-data/ folder.

Skipped wherever that folder is absent (CI, other machines).
"""
from pathlib import Path

import pytest

from acaddoc.schema import Course
from acaddoc.validate import validate

PRIVATE = Path(__file__).resolve().parents[2] / "private-data" / "courses"
pytestmark = pytest.mark.skipif(not PRIVATE.is_dir(), reason="no private-data/courses")


def rules(code):
    c = Course.model_validate_json((PRIVATE / f"{code}.json").read_text(encoding="utf-8"))
    return {i.rule for i in validate(c)}


def test_known_inconsistencies_in_the_real_syllabi_are_found():
    # module hours sum to 47 and 64 against 48 contact classes
    assert "MODULE_HOURS_SUM" in rules("ACSE10")
    assert "MODULE_HOURS_SUM" in rules("AHSE04")
    assert "MODULE_HOURS_MISSING" in rules("AHSE02")

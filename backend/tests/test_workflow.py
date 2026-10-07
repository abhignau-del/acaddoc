"""Who may do what, in which state (pure rules, no database)."""
import pytest

from acaddoc.auth import User
from acaddoc.workflow import ACTIONS, Meta, permissions, why_not

ADMIN = User("a", "admin", "Admin", "admin")
FAC = User("f", "fac", "Faculty", "faculty", "CSE")
FAC2 = User("f2", "fac2", "Faculty 2", "faculty", "CSE")
HOD = User("h", "hod", "HOD CSE", "hod", "CSE")
HOD_ECE = User("he", "hodece", "HOD ECE", "hod", "ECE")
DEAN = User("d", "dean", "Dean", "dean")


def meta(status="draft", owner="f", dept="CSE", version=0, approved=None):
    return Meta("CSE205", dept, owner, status, version, approved)


def allowed(u, action, m):
    return why_not(u, action, m) is None


@pytest.mark.parametrize("status,editable", [
    ("draft", True), ("revision_required", True), ("submitted", False), ("hod_approved", False), ("approved", False)])
def test_only_drafts_and_revisions_are_editable(status, editable):
    assert allowed(FAC, "edit", meta(status)) is editable
    assert allowed(ADMIN, "edit", meta(status)) is editable


def test_only_owner_or_admin_edits():
    assert not allowed(FAC2, "edit", meta())
    assert not allowed(HOD, "edit", meta())
    assert not allowed(DEAN, "edit", meta())


def test_happy_path_roles():
    assert allowed(FAC, "submit", meta("draft"))
    assert allowed(HOD, "hod_approve", meta("submitted"))
    assert allowed(DEAN, "approve", meta("hod_approved"))
    assert allowed(FAC, "reopen", meta("approved", version=1, approved=1))


def test_hod_reviews_only_own_department():
    assert not allowed(HOD_ECE, "hod_approve", meta("submitted"))
    assert "HOD of CSE" in why_not(HOD_ECE, "hod_approve", meta("submitted"))


def test_stage_decides_who_can_send_back():
    assert allowed(HOD, "request_revision", meta("submitted"))
    assert not allowed(DEAN, "request_revision", meta("submitted"))
    assert allowed(DEAN, "request_revision", meta("hod_approved"))
    assert not allowed(HOD, "request_revision", meta("hod_approved"))


def test_nobody_reviews_their_own_course():
    own = meta("submitted", owner="h")
    assert "own" in why_not(HOD, "hod_approve", own)
    assert "own" in why_not(DEAN, "approve", meta("hod_approved", owner="d"))


def test_admin_cannot_approve_and_faculty_cannot_skip_stages():
    for u in (ADMIN, FAC):
        assert not allowed(u, "hod_approve", meta("submitted", owner="x"))
        assert not allowed(u, "approve", meta("hod_approved", owner="x"))
    assert not allowed(DEAN, "approve", meta("submitted"))   # HOD must go first


def test_wrong_state_is_refused_for_every_action():
    for action, (sources, _) in ACTIONS.items():
        for status in {"draft", "submitted", "hod_approved", "approved", "revision_required"} - sources:
            assert not allowed(ADMIN, action, meta(status)) and not allowed(DEAN, action, meta(status)), (action, status)


def test_submitted_courses_cannot_be_deleted():
    assert allowed(FAC, "delete", meta())
    assert not allowed(FAC, "delete", meta("revision_required", version=1))
    assert not allowed(ADMIN, "delete", meta("draft", version=2, approved=1))
    assert not allowed(FAC2, "delete", meta())


def test_disabled_users_can_do_nothing():
    gone = User("f", "fac", "Faculty", "faculty", "CSE", disabled=True)
    assert not any(permissions(gone, meta()).values())


def test_unowned_course_is_admin_only():
    orphan = meta(owner=None)
    assert allowed(ADMIN, "edit", orphan) and not allowed(FAC, "edit", orphan)

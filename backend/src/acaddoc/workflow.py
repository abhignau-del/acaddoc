"""Approval workflow: who may do what to a course, and in which state.

    draft ── submit ──▶ submitted ── hod_approve ──▶ hod_approved ── approve ──▶ approved

    submitted    ── withdraw ──────────▶ draft              (author takes it back)
    submitted    ── request_revision ──▶ revision_required  (HOD sends it back)
    hod_approved ── request_revision ──▶ revision_required  (dean sends it back)
    revision_required ── submit ───────▶ submitted
    approved     ── reopen ────────────▶ draft              (start the next version)

Rules
- Only drafts and courses sent back for revision can be edited, by their owner or an admin.
- The HOD of the course's department makes the first review; the dean the final one.
- Nobody reviews a course they own.
- Each submission freezes a numbered version. An approved version is never changed:
  reopening starts the next version while the approved one stays in force.

Pure functions only; the API applies them and the store records the result.
"""
from __future__ import annotations

from dataclasses import dataclass

from .auth import User

STATUSES = ("draft", "submitted", "hod_approved", "approved", "revision_required")
LABELS = {
    "draft": "Draft", "submitted": "Awaiting HOD", "hod_approved": "Awaiting dean",
    "approved": "Approved", "revision_required": "Revision required",
}

# action -> (states it may start from, state it leads to)
ACTIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit": (frozenset({"draft", "revision_required"}), "submitted"),
    "withdraw": (frozenset({"submitted"}), "draft"),
    "hod_approve": (frozenset({"submitted"}), "hod_approved"),
    "approve": (frozenset({"hod_approved"}), "approved"),
    "request_revision": (frozenset({"submitted", "hod_approved"}), "revision_required"),
    "reopen": (frozenset({"approved"}), "draft"),
}
NEEDS_COMMENT = {"request_revision"}
EDITABLE = frozenset({"draft", "revision_required"})


@dataclass(frozen=True)
class Meta:
    """The workflow facts about one course (its content lives elsewhere)."""
    code: str
    department: str
    owner_id: str | None
    status: str = "draft"
    version: int = 0                     # number of the last submitted version (0 = never submitted)
    approved_version: int | None = None  # the version currently in force


def _owner_or_admin(u: User, m: Meta) -> bool:
    return u.is_admin or (m.owner_id is not None and u.id == m.owner_id)


def _reviewer(u: User, m: Meta, stage: str) -> str | None:
    if m.owner_id == u.id:
        return "you cannot review a course you own"
    if stage == "hod":
        if u.role != "hod":
            return "only a head of department reviews at this stage"
        if u.department != m.department:
            return f"only the HOD of {m.department or 'the course department'} reviews this course"
        return None
    if u.role != "dean":
        return "only the dean gives final approval"
    return None


def why_not(u: User, action: str, m: Meta) -> str | None:
    """None when `u` may perform `action` on the course now, otherwise the reason it may not."""
    if u.disabled:
        return "this account is disabled"
    if action == "edit":
        if m.status not in EDITABLE:
            return f"a course that is {LABELS[m.status].lower()} cannot be edited"
        return None if _owner_or_admin(u, m) else "only the course owner or an admin can edit it"
    if action == "delete":
        if m.approved_version is not None or m.version > 0:
            return "a course that has been submitted keeps its history and cannot be deleted"
        return None if _owner_or_admin(u, m) else "only the course owner or an admin can delete it"
    if action not in ACTIONS:
        return f"unknown action {action}"
    sources, _ = ACTIONS[action]
    if m.status not in sources:
        return f"not possible while the course is {LABELS[m.status].lower()}"
    if action in ("submit", "withdraw", "reopen"):
        return None if _owner_or_admin(u, m) else "only the course owner or an admin can do this"
    if action == "hod_approve":
        return _reviewer(u, m, "hod")
    if action == "approve":
        return _reviewer(u, m, "dean")
    if action == "request_revision":
        return _reviewer(u, m, "hod" if m.status == "submitted" else "dean")
    return "not allowed"


def permissions(u: User, m: Meta) -> dict[str, bool]:
    return {a: why_not(u, a, m) is None for a in ("edit", "delete", *ACTIONS)}


def next_status(action: str) -> str:
    return ACTIONS[action][1]

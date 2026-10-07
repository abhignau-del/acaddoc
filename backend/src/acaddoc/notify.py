"""Email notifications for the approval workflow.

Who hears about what:
    submit           -> HOD(s) of the course's department   "waiting for your review"
    hod_approve      -> dean(s)                              "waiting for final approval"
    request_revision -> course owner, with the reviewer's note
    approve          -> course owner
    withdraw         -> HOD(s) of the department              "no longer waiting"
Nobody is told about their own action; disabled accounts and accounts without an
address are skipped.

Every message goes into the outbox table first, then is sent after the HTTP
response, so a slow or broken mail server never blocks the workflow. Without
mail settings, messages are still recorded (status "not_configured").

Settings (environment):
    ACADDOC_SMTP_HOST, ACADDOC_SMTP_PORT (587), ACADDOC_SMTP_USER, ACADDOC_SMTP_PASSWORD,
    ACADDOC_SMTP_SECURITY = starttls (default) | ssl | none,
    ACADDOC_MAIL_FROM (defaults to the SMTP user),
    ACADDOC_PUBLIC_URL  e.g. https://acaddoc.example.edu  (for links in emails)
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import quote

from .auth import User
from .store import Record, Store

AUDIENCE = {
    "submit": "hod", "withdraw": "hod", "hod_approve": "dean",
    "request_revision": "owner", "approve": "owner",
}


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


@dataclass(frozen=True)
class SmtpMailer:
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    security: str = "starttls"
    sender: str = ""
    timeout: float = 20.0

    @classmethod
    def from_env(cls, env=os.environ) -> "SmtpMailer | None":
        host = env.get("ACADDOC_SMTP_HOST", "").strip()
        if not host:
            return None
        security = env.get("ACADDOC_SMTP_SECURITY", "starttls").strip().lower()
        if security not in ("starttls", "ssl", "none"):
            raise ValueError("ACADDOC_SMTP_SECURITY must be starttls, ssl or none")
        user = env.get("ACADDOC_SMTP_USER", "").strip()
        default_port = 465 if security == "ssl" else 587
        return cls(host=host, port=int(env.get("ACADDOC_SMTP_PORT") or default_port), user=user,
                   password=env.get("ACADDOC_SMTP_PASSWORD", ""), security=security,
                   sender=env.get("ACADDOC_MAIL_FROM", "").strip() or user)

    def describe(self) -> dict:
        return {"configured": True, "host": self.host, "port": self.port, "security": self.security,
                "sender": self.sender}

    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, mail.to, mail.subject
        msg.set_content(mail.body)
        ctx = ssl.create_default_context()
        if self.security == "ssl":
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ctx)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        with server:
            if self.security == "starttls":
                server.starttls(context=ctx)
            if self.user:
                server.login(self.user, self.password)
            server.send_message(msg)


def recipients(store: Store, action: str, r: Record, actor: User) -> list[User]:
    who = AUDIENCE.get(action)
    if who is None:
        return []
    if who == "owner":
        found = [u for u in store.users() if u.id == r.meta.owner_id]
    elif who == "hod":
        found = [u for u in store.users() if u.role == "hod" and u.department == r.meta.department]
    else:
        found = [u for u in store.users() if u.role == "dean"]
    return [u for u in found if u.id != actor.id and not u.disabled and u.email]


def link(base_url: str, code: str) -> str:
    return f"{base_url.rstrip('/')}/#course={quote(code)}" if base_url else ""


def compose(action: str, r: Record, actor: User, to: User, comment: str, base_url: str) -> Mail:
    c = r.course
    name = f"{c.course_code} {c.course_title}"
    v = f" (version {r.meta.version})" if r.meta.version else ""
    subject, lines = {
        "submit": (f"[AcadDoc] {name} is waiting for your review",
                   [f"{actor.display_name} submitted {name}{v} for review.",
                    "As HOD of the department, please approve it or send it back with a note."]),
        "hod_approve": (f"[AcadDoc] {name} is waiting for final approval",
                        [f"{actor.display_name} (HOD) approved {name}{v}.",
                         "It now needs your final approval."]),
        "request_revision": (f"[AcadDoc] {name} was sent back for revision",
                             [f"{actor.display_name} sent {name}{v} back for revision.", "", "Their note:",
                              *("    " + ln for ln in comment.splitlines()), "",
                              "Make the changes and submit it again."]),
        "approve": (f"[AcadDoc] {name} is approved",
                    [f"{actor.display_name} gave final approval to {name}{v}.",
                     "This version will now be used in programme handbooks."]),
        "withdraw": (f"[AcadDoc] {name} was withdrawn from review",
                     [f"{actor.display_name} withdrew {name} from review. Nothing is waiting for you on it."]),
    }[action]
    url = link(base_url, c.course_code)
    body = "\n".join([f"Dear {to.display_name},", "", *lines, "", *( [f"Open the course: {url}", ""] if url else []),
                      "-- ", "AcadDoc. You receive this because of your role in course approval."])
    return Mail(to.email, subject, body)


def queue(store: Store, mailer: Mailer | None, action: str, r: Record, actor: User, comment: str,
          base_url: str) -> list[int]:
    """Record the messages for this workflow step; returns the outbox ids to send."""
    ids = []
    for u in recipients(store, action, r, actor):
        m = compose(action, r, actor, u, comment, base_url)
        mid = store.queue_mail(m.to, m.subject, m.body, status="queued" if mailer else "not_configured")
        if mailer:
            ids.append(mid)
    return ids


def deliver(store: Store, mailer: Mailer, ids: list[int]) -> None:
    """Send queued messages, recording the outcome of each. Never raises."""
    for mid in ids:
        row = store.mail(mid)
        try:
            mailer.send(Mail(row["to_addr"], row["subject"], row["body"]))
        except Exception as e:   # noqa: BLE001 - any failure is recorded, none may escape
            store.mark_mail(mid, "failed", f"{type(e).__name__}: {e}")
        else:
            store.mark_mail(mid, "sent")

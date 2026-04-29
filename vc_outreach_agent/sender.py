"""SMTP sender — picks up drafts in queue/approved/ and ships them via SMTP.

Auth: SMTP_HOST + SMTP_PORT + SMTP_USER + SMTP_PASSWORD env vars. Most
common configs:
  Gmail (App Password): smtp.gmail.com:587, your gmail + 16-char app password
  Postmark:             smtp.postmarkapp.com:587, server token as both user+pass
  Resend:               smtp.resend.com:465, "resend" as user, API key as pass
  Sendgrid:             smtp.sendgrid.net:587, "apikey" as user, API key as pass

After sending, moves the draft from queue/approved/ → queue/sent/ so the
next run doesn't double-send.

Dry-run mode: SENDER_DRY_RUN=1 (or --dry-run flag) skips the actual SMTP
call but still does the file move. Useful for testing the pipeline without
burning sends.

Designed defensively: if SMTP fails for one draft, log + skip; continue
with the rest. Never raises out of `send_approved_queue()`.

v0.4: HITL queue logic lifted to solo_founder_os.HitlQueue. This module
now only handles SMTP transport + the markdown-body parser specific to
the vc-outreach draft format.
"""
from __future__ import annotations
import os
import pathlib
import re
import smtplib
import ssl
import sys
import time
from email.mime.text import MIMEText

from solo_founder_os.hitl_queue import parse_frontmatter

from .queue import _queue


# Default rate limit: 10 sends/min = one every 6s. Gmail App Password caps
# at 100/day so even at this rate you can't blow the daily limit in 10 min.
# Override via SENDER_RATE_LIMIT_PER_MIN env (or --rate-limit CLI flag).
DEFAULT_RATE_LIMIT_PER_MIN = 10


# Re-exported for backward compatibility with v0.3 tests
_parse_frontmatter = parse_frontmatter


def _queue_root() -> pathlib.Path:
    """Legacy accessor — returns the resolved queue root for tests that
    import this directly. New code should use _queue().root."""
    return _queue().root


def _extract_section(md_text: str, header: str) -> str:
    """Return the body text under a `# header` until the next `#` block.
    Empty string if not found."""
    pattern = rf"^# {re.escape(header)}\s*\n(.*?)(?=\n#\s|\n---\s|\Z)"
    m = re.search(pattern, md_text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def send_one(path: pathlib.Path, *, dry_run: bool = False) -> tuple[bool, str]:
    """Send the email represented by `path`. Return (success, reason).
    Caller is responsible for moving the file on success."""
    md = path.read_text()
    fm = parse_frontmatter(md)
    to_email = fm.get("investor_email", "").strip()
    if not to_email:
        return False, "missing investor_email in frontmatter"

    subject = fm.get("subject", "").strip() or _extract_section(md, "Subject")
    body = _extract_section(md, "Body")
    if not subject or not body:
        return False, "missing subject or body section"

    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or smtp_user
    if not smtp_host or not smtp_user or not smtp_pass or not from_addr:
        return False, ("missing SMTP env vars "
                       "(SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM)")

    if dry_run or os.getenv("SENDER_DRY_RUN") == "1":
        return True, f"dry-run OK (would send to {to_email})"

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    try:
        if smtp_port == 465:
            # Implicit TLS
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx,
                                   timeout=30) as s:
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
    except Exception as e:
        return False, f"SMTP error: {e}"

    return True, "sent"


def send_approved_queue(*, dry_run: bool = False,
                        rate_limit_per_min: int | None = None,
                        sleep_fn=time.sleep) -> dict[str, list[str]]:
    """Iterate queue/approved/, send each, move successes to queue/sent/.

    Rate-limiting: defaults to DEFAULT_RATE_LIMIT_PER_MIN = 10/min between
    successful sends (Gmail App Password caps at 100/day; 10/min × 10 min
    is the worst burst that's still safe). Override via the CLI flag,
    SENDER_RATE_LIMIT_PER_MIN env, or rate_limit_per_min=0 to disable.

    `sleep_fn` is injectable for tests.

    Returns {"sent": [paths], "failed": [(path, reason)], "skipped": []}.
    Never raises.
    """
    q = _queue()

    if rate_limit_per_min is None:
        rate_limit_per_min = int(os.getenv(
            "SENDER_RATE_LIMIT_PER_MIN", str(DEFAULT_RATE_LIMIT_PER_MIN)))
    sleep_seconds = (60.0 / rate_limit_per_min) if rate_limit_per_min > 0 else 0.0

    summary: dict[str, list] = {"sent": [], "failed": [], "skipped": []}
    paths = q.list(status=q.APPROVED)
    if not paths:
        return summary

    for i, path in enumerate(paths):
        ok, reason = send_one(path, dry_run=dry_run)
        if ok:
            try:
                new_path = q.move(path, to=q.SENT)
            except Exception:
                summary["sent"].append(str(path))
                print(f"⚠ sent but couldn't move {path.name}: {reason}",
                      file=sys.stderr)
                continue
            summary["sent"].append(str(new_path))
            print(f"✓ sent {path.name} → {new_path.name}", file=sys.stderr)
            # Respect rate limit between successful sends only (not after
            # failures — those are usually fast and shouldn't count against
            # provider rate; let the caller retry).
            if sleep_seconds > 0 and i < len(paths) - 1 and not dry_run:
                sleep_fn(sleep_seconds)
        else:
            summary["failed"].append((str(path), reason))
            print(f"✗ {path.name}: {reason}", file=sys.stderr)

    return summary

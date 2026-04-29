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
"""
from __future__ import annotations
import os
import pathlib
import re
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText


# Re-exported for tests; the real path is read at call time so tests can
# override via VC_OUTREACH_QUEUE.
def _queue_root() -> pathlib.Path:
    return pathlib.Path(os.getenv(
        "VC_OUTREACH_QUEUE",
        str(pathlib.Path.home() / ".vc-outreach-agent" / "queue"),
    ))


# YAML frontmatter parser — same minimalist format we use in queue.py
_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(md_text: str) -> dict:
    """Return the YAML frontmatter as a dict. Returns {} if missing."""
    m = _FM_RE.match(md_text)
    if not m:
        return {}
    out: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


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
    fm = _parse_frontmatter(md)
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


def send_approved_queue(*, dry_run: bool = False) -> dict[str, list[str]]:
    """Iterate queue/approved/, send each, move successes to queue/sent/.
    Returns {"sent": [paths], "failed": [(path, reason)], "skipped": []}.
    Never raises.
    """
    root = _queue_root()
    approved_dir = root / "approved"
    sent_dir = root / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, list] = {"sent": [], "failed": [], "skipped": []}
    if not approved_dir.exists():
        return summary

    for path in sorted(approved_dir.glob("*.md")):
        ok, reason = send_one(path, dry_run=dry_run)
        if ok:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            new_path = sent_dir / f"{ts}-{path.name}"
            try:
                path.rename(new_path)
            except Exception:
                # Couldn't move file; the email may have been sent — log
                # and don't retry.
                summary["sent"].append(str(path))
                print(f"⚠ sent but couldn't move {path.name}: {reason}",
                      file=sys.stderr)
                continue
            summary["sent"].append(str(new_path))
            print(f"✓ sent {path.name} → {new_path.name}", file=sys.stderr)
        else:
            summary["failed"].append((str(path), reason))
            print(f"✗ {path.name}: {reason}", file=sys.stderr)

    return summary

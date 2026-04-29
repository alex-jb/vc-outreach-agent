"""HITL queue — every draft lands in queue/pending/ as markdown for human
review. The human moves the file to queue/approved/ (will be sent), or
queue/rejected/ (won't), or just edits in place and re-saves.

Sending happens elsewhere (a `send` subcommand of the CLI iterates
queue/approved/ and ships via SMTP or whatever sender you wire). v0.1 only
queues; v0.2 will add the SMTP sender + reply tracking.

Why markdown not JSON / DB: founder can review on their phone in Obsidian
during a coffee break, edit a sentence, save. Zero infra.
"""
from __future__ import annotations
import os
import pathlib
import re
from datetime import datetime
from .models import Draft


QUEUE_ROOT = os.getenv("VC_OUTREACH_QUEUE",
                       str(pathlib.Path.home() / ".vc-outreach-agent" / "queue"))


def _sanitize(s: str) -> str:
    """Filename-safe: alnum + dashes only."""
    return re.sub(r"[^a-zA-Z0-9-]+", "-", s).strip("-").lower() or "x"


def queue_draft(draft: Draft, *, status: str = "pending") -> pathlib.Path:
    """Write the draft as markdown to queue/<status>/<timestamp>-<slug>.md.

    Status is one of pending / approved / rejected / sent. Default pending.
    """
    root = pathlib.Path(QUEUE_ROOT) / status
    root.mkdir(parents=True, exist_ok=True)

    ts = (draft.drafted_at or datetime.utcnow()).strftime("%Y%m%dT%H%M%S")
    slug_inv = _sanitize(draft.investor_name or draft.investor_email.split("@")[0])
    slug_proj = _sanitize(draft.project_name or "x")
    path = root / f"{ts}-{slug_proj}-to-{slug_inv}.md"

    md = f"""---
project: {draft.project_name}
investor_name: {draft.investor_name}
investor_email: {draft.investor_email}
subject: {draft.subject}
status: {status}
drafted_at: {draft.drafted_at.isoformat() if draft.drafted_at else ''}
---

# Subject
{draft.subject}

# Body
{draft.body}

---
<!-- Move this file to queue/approved/ to send, or queue/rejected/ to skip. -->
<!-- Edit the body above first if needed. -->

## Audit
- Prompt sent to LLM:
```
{draft.raw_prompt[:1500]}
```

- Raw LLM response:
```
{draft.raw_response[:1500]}
```
"""
    path.write_text(md)
    return path


def list_queue(*, status: str = "pending") -> list[pathlib.Path]:
    """Return all draft files at the given status."""
    root = pathlib.Path(QUEUE_ROOT) / status
    if not root.exists():
        return []
    return sorted(root.glob("*.md"))

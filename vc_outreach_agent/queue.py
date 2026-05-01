"""HITL markdown queue — thin agent-specific layer over solo-founder-os HitlQueue.

The shared library handles directory layout, file naming, frontmatter,
status transitions. This module renders the agent-specific markdown body
(YAML frontmatter + # Subject / # Body sections + audit trail) and
exposes the same public functions the v0.2 callers expected.
"""
from __future__ import annotations
import os
import pathlib

from solo_founder_os.hitl_queue import (
    HitlQueue,
    make_basename,
    PENDING,
)

from .models import Draft


DEFAULT_QUEUE_ROOT = (pathlib.Path.home()
                     / ".vc-outreach-agent" / "queue")


def _queue() -> HitlQueue:
    """Build a HitlQueue honoring the legacy VC_OUTREACH_QUEUE env var."""
    return HitlQueue.from_env("VC_OUTREACH_QUEUE", default=DEFAULT_QUEUE_ROOT)


def _render_markdown(draft: Draft, status: str) -> str:
    """vc-outreach's agent-specific layout. Frontmatter for machine-readable
    metadata, plain markdown sections for human review."""
    return f"""---
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


def queue_draft(draft: Draft, *, status: str = PENDING) -> pathlib.Path:
    """Write the draft as markdown under queue/<status>/. Returns path."""
    basename = make_basename(
        [draft.project_name or "x", "to",
         draft.investor_name or draft.investor_email.split("@")[0]],
        ts=draft.drafted_at,
    )
    return _queue().write(basename, _render_markdown(draft, status),
                          status=status)


def list_queue(*, status: str = PENDING) -> list[pathlib.Path]:
    """Return all draft files at the given status. Sorted by name (== timestamp)."""
    return _queue().list(status=status)


# Re-export for legacy callers that imported the underscore-prefixed
# helper. New code should import from solo_founder_os directly.
QUEUE_ROOT = os.getenv("VC_OUTREACH_QUEUE", str(DEFAULT_QUEUE_ROOT))

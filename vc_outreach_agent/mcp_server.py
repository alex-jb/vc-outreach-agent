"""MCP server — let Claude Desktop / Cursor / Zed draft VC cold emails
inline. Ask "draft an intro to {investor} for my project" and the
assistant calls draft_email() and returns a personalized draft.

Tools:
  - draft_email(investor_name, investor_email, ..., project_name, one_liner, ...)
        Draft one personalized email. All extra fields optional.
  - list_pending()
        Show drafts currently waiting for human review (HITL queue).
  - list_approved()
        Show drafts approved + ready to send via SMTP.

Install:
    pip install vc-outreach-agent[mcp]

Wire to Claude Desktop:

    {
      "mcpServers": {
        "vc-outreach": {
          "command": "vc-outreach-mcp",
          "env": { "ANTHROPIC_API_KEY": "..." }
        }
      }
    }
"""
from __future__ import annotations
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print("vc-outreach-mcp requires the `mcp` package. "
          "Install with: pip install 'vc-outreach-agent[mcp]'",
          file=sys.stderr)
    raise SystemExit(1) from e

from solo_founder_os.hitl_queue import APPROVED, PENDING

from .drafter import draft_email as _draft_email
from .models import Investor, Project
from .queue import list_queue, queue_draft


mcp = FastMCP("vc-outreach")


@mcp.tool()
def draft_email(
    investor_name: str,
    investor_email: str,
    project_name: str,
    one_liner: str,
    investor_firm: str = "",
    thesis_hint: str = "",
    traction: list[str] | None = None,
    stage: str = "",
    raise_amount: str = "",
    deck_url: str = "",
    founder_name: str = "",
    why_now: str = "",
    save_to_queue: bool = False,
) -> str:
    """Draft a personalized cold email for one (investor, project) pair.

    Args:
        investor_name, investor_email: required.
        project_name, one_liner: required project summary.
        investor_firm, thesis_hint: helpful for personalization.
        traction: list of concrete metric strings, e.g.
                  ["Sharpe 1.41 over 698 backtests", "5 paying users"].
        save_to_queue: if True, drop the draft into the HITL pending/
                       directory for review before sending.

    Returns: markdown-formatted draft (subject + body + raw_response).
    """
    inv = Investor(
        name=investor_name,
        email=investor_email,
        firm=investor_firm,
        thesis_hint=thesis_hint,
    )
    proj = Project(
        name=project_name,
        one_liner=one_liner,
        traction=traction or [],
        stage=stage,
        raise_amount=raise_amount,
        deck_url=deck_url,
        founder_name=founder_name,
        why_now=why_now,
    )
    draft = _draft_email(inv, proj)
    out = [
        f"### To: {draft.investor_email}",
        f"### Subject: {draft.subject}",
        "",
        draft.body,
    ]
    if save_to_queue:
        path = queue_draft(draft, status=PENDING)
        out.append("")
        out.append(f"📥 saved to HITL queue: `{path}`")
    if draft.raw_response and "fell back" in draft.raw_response:
        out.append("")
        out.append(f"_{draft.raw_response}_")
    return "\n".join(out)


@mcp.tool()
def list_pending() -> str:
    """List drafts in the HITL pending/ queue (waiting for human review)."""
    paths = list_queue(status=PENDING)
    if not paths:
        return "No drafts pending review."
    return "Pending drafts:\n" + "\n".join(f"- {p}" for p in paths)


@mcp.tool()
def list_approved() -> str:
    """List drafts in approved/ — ready to send via SMTP."""
    paths = list_queue(status=APPROVED)
    if not paths:
        return "No approved drafts ready to send."
    return "Approved drafts:\n" + "\n".join(f"- {p}" for p in paths)


def main() -> None:
    """Console-script entry point. Runs the MCP server over stdio."""
    if os.getenv("VC_OUTREACH_SKIP") == "1":
        return
    mcp.run()


if __name__ == "__main__":
    main()

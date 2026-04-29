"""CLI entry — vc-outreach-agent.

Modes:
    draft  --project orallexa.yml --investors investors.csv  → fan-drafts
                                                              into HITL queue
    queue  [--status pending|approved|rejected|sent]          → list queue

Bypass: VC_OUTREACH_SKIP=1 makes the agent a no-op.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from pathlib import Path

from .drafter import draft_email
from .models import Investor, Project
from .queue import queue_draft, list_queue
from .sender import send_approved_queue


def _load_project(path: str) -> Project:
    """Project file is YAML-ish or JSON. We avoid the PyYAML dep — accept
    either JSON or a tiny key:value text format."""
    raw = Path(path).read_text()
    if path.endswith(".json"):
        data = json.loads(raw)
    else:
        # Minimal YAML-ish parser: key: value, list with - prefix
        data = {}
        current_list_key: str | None = None
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("  - "):
                if current_list_key:
                    data.setdefault(current_list_key, []).append(line[4:].strip())
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                if not v:  # list follows
                    current_list_key = k
                    data[k] = []
                else:
                    current_list_key = None
                    data[k] = v
    return Project(
        name=data.get("name", ""),
        one_liner=data.get("one_liner", ""),
        traction=data.get("traction", []) if isinstance(data.get("traction"), list)
                 else [data.get("traction", "")],
        stage=data.get("stage", ""),
        raise_amount=data.get("raise_amount", ""),
        deck_url=data.get("deck_url", ""),
        founder_name=data.get("founder_name", ""),
        founder_email=data.get("founder_email", ""),
        why_now=data.get("why_now", ""),
    )


def _load_investors(path: str) -> list[Investor]:
    """Investors file is CSV with columns: name,email,firm,role,thesis_hint,linkedin,twitter,notes"""
    out: list[Investor] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("email"):
                continue
            out.append(Investor(
                name=row.get("name", "").strip(),
                email=row["email"].strip(),
                firm=row.get("firm", "").strip(),
                role=row.get("role", "").strip(),
                thesis_hint=row.get("thesis_hint", "").strip(),
                linkedin=row.get("linkedin", "").strip(),
                twitter=row.get("twitter", "").strip(),
                notes=row.get("notes", "").strip(),
            ))
    return out


def cmd_draft(args) -> int:
    proj = _load_project(args.project)
    investors = _load_investors(args.investors)
    if not investors:
        print(f"⚠ no investors loaded from {args.investors}", file=sys.stderr)
        return 1

    print(f"drafting {len(investors)} email(s) for {proj.name} → HITL queue",
          file=sys.stderr)
    for i, inv in enumerate(investors, 1):
        d = draft_email(inv, proj)
        path = queue_draft(d)
        print(f"  [{i}/{len(investors)}] {inv.name} <{inv.email}> → {path.name}",
              file=sys.stderr)
    print("\n✓ done. review at:")
    print(f"  {Path(os.getenv('VC_OUTREACH_QUEUE', '')) or path.parent.parent}/pending/",
          file=sys.stderr)
    return 0


def cmd_queue(args) -> int:
    paths = list_queue(status=args.status)
    if not paths:
        print(f"(no drafts in queue/{args.status}/)", file=sys.stderr)
        return 0
    for p in paths:
        print(p)
    return 0


def cmd_send(args) -> int:
    summary = send_approved_queue(dry_run=args.dry_run)
    print(f"\n  sent:    {len(summary['sent'])}", file=sys.stderr)
    print(f"  failed:  {len(summary['failed'])}", file=sys.stderr)
    if summary["failed"]:
        for path, reason in summary["failed"]:
            print(f"    ✗ {path}: {reason}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if os.getenv("VC_OUTREACH_SKIP") == "1":
        return 0

    p = argparse.ArgumentParser(
        prog="vc-outreach-agent",
        description="Find investors + draft personalized cold emails into a HITL queue.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft", help="Draft emails for one project × N investors")
    d.add_argument("--project", required=True,
                   help="Path to project file (.json or simple .yml)")
    d.add_argument("--investors", required=True,
                   help="Path to investors CSV (columns: name,email,firm,role,thesis_hint,...)")

    q = sub.add_parser("queue", help="List drafts in queue")
    q.add_argument("--status", default="pending",
                   choices=["pending", "approved", "rejected", "sent"])

    s = sub.add_parser("send", help="Send all queue/approved/ drafts via SMTP")
    s.add_argument("--dry-run", action="store_true",
                   help="Don't actually send; print what would happen")

    args = p.parse_args(argv)

    if args.cmd == "draft":
        return cmd_draft(args)
    if args.cmd == "queue":
        return cmd_queue(args)
    if args.cmd == "send":
        return cmd_send(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

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

from .drafter import draft_email, draft_email_customer
from .enricher import enrich_csv_file
from .models import CustomerProject, Investor, Lead, Project
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
    summary = send_approved_queue(
        dry_run=args.dry_run,
        rate_limit_per_min=args.rate_limit,
    )
    print(f"\n  sent:    {len(summary['sent'])}", file=sys.stderr)
    print(f"  failed:  {len(summary['failed'])}", file=sys.stderr)
    if summary["failed"]:
        for path, reason in summary["failed"]:
            print(f"    ✗ {path}: {reason}", file=sys.stderr)
        return 1
    return 0


def _load_customer_project(path: str) -> CustomerProject:
    raw = Path(path).read_text()
    if path.endswith(".json"):
        data = json.loads(raw)
    else:
        data = {}
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                data[k.strip()] = v.strip()
    return CustomerProject(
        name=data.get("name", ""),
        one_liner=data.get("one_liner", ""),
        differentiator=data.get("differentiator", ""),
        free_offer=data.get("free_offer", ""),
        paid_tier=data.get("paid_tier", ""),
        proof_url=data.get("proof_url", ""),
        founder_name=data.get("founder_name", ""),
        founder_email=data.get("founder_email", ""),
    )


def _load_leads(path: str) -> list[Lead]:
    """Leads CSV columns: email,signal_source,signal_text,name,handle,notes."""
    out: list[Lead] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("email") or not row.get("signal_text", "").strip():
                # Customer-mode hard gate: signal_text required
                continue
            out.append(Lead(
                email=row["email"].strip(),
                signal_source=row.get("signal_source", "").strip(),
                signal_text=row["signal_text"].strip(),
                name=row.get("name", "").strip(),
                handle=row.get("handle", "").strip(),
                notes=row.get("notes", "").strip(),
            ))
    return out


def cmd_customer_draft(args) -> int:
    proj = _load_customer_project(args.project)
    leads = _load_leads(args.leads)
    if not leads:
        print(f"⚠ no leads loaded from {args.leads} (rows without "
              f"signal_text are dropped — customer mode requires verbatim "
              f"signals)", file=sys.stderr)
        return 1

    print(f"drafting {len(leads)} customer-mode email(s) for {proj.name} "
          f"→ HITL queue", file=sys.stderr)
    last_path = None
    for i, lead in enumerate(leads, 1):
        try:
            d = draft_email_customer(lead, proj)
        except ValueError as e:
            print(f"  [{i}/{len(leads)}] {lead.email}: skipped — {e}",
                  file=sys.stderr)
            continue
        last_path = queue_draft(d)
        print(f"  [{i}/{len(leads)}] {lead.name or lead.email} → "
              f"{last_path.name}", file=sys.stderr)
    if last_path:
        print("\n✓ done. review at:", file=sys.stderr)
        print(f"  {last_path.parent}/", file=sys.stderr)
    return 0


def cmd_enrich(args) -> int:
    summary = enrich_csv_file(
        csv_path=args.investors,
        digest_path=args.digest,
        out_path=args.out,
        top_n_clusters=args.top_n,
    )
    print(f"enriched {summary['enriched']} of {summary['rows_total']} "
          f"investor rows from {args.digest}",
          file=sys.stderr)
    if args.out:
        print(f"  wrote to {args.out}", file=sys.stderr)
    else:
        print(f"  (overwrote {args.investors})", file=sys.stderr)
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
    s.add_argument("--rate-limit", type=int, default=None,
                   help="Max sends per minute (default: SENDER_RATE_LIMIT_PER_MIN "
                        "env, or 10 if unset). 0 = no rate limit. "
                        "Gmail App Password caps at 100/day.")

    e = sub.add_parser("enrich",
        help="Fill investors CSV thesis_hint column from a CDA digest")
    e.add_argument("--investors", required=True,
                   help="Path to investors.csv (modified in-place if --out absent)")
    e.add_argument("--digest", required=True,
                   help="Path to customer-discovery-agent digest.md")
    e.add_argument("--out", default=None,
                   help="Optional output path (default: overwrite --investors)")
    e.add_argument("--top-n", type=int, default=3,
                   help="Use the top N clusters from the digest, rotated across rows (default 3)")

    cd = sub.add_parser(
        "customer-draft",
        help="(merged from customer-outreach-agent v0.2) Draft customer-mode "
             "cold emails — Lead + CustomerProject. Each lead must have a "
             "verbatim signal_text or it is skipped.",
    )
    cd.add_argument("--project", required=True,
                    help="Path to customer-project file (.json or simple .yml)")
    cd.add_argument("--leads", required=True,
                    help="Path to leads CSV (columns: email,signal_source,"
                         "signal_text,name,handle,notes). Rows without "
                         "signal_text are dropped.")

    args = p.parse_args(argv)

    if args.cmd == "draft":
        return cmd_draft(args)
    if args.cmd == "queue":
        return cmd_queue(args)
    if args.cmd == "send":
        return cmd_send(args)
    if args.cmd == "enrich":
        return cmd_enrich(args)
    if args.cmd == "customer-draft":
        return cmd_customer_draft(args)
    return 1


def main_customer(argv: list[str] | None = None) -> int:
    """Entry point for the `customer-outreach-agent` console_script alias.

    Maps the legacy `customer-outreach-agent draft ...` invocation onto the
    merged `vc-outreach-agent customer-draft ...` flow. Existing shell history
    + cron jobs that invoke `customer-outreach-agent draft --project p.json
    --leads leads.csv` keep working unchanged.
    """
    if argv is None:
        argv = sys.argv[1:]
    # Translate `draft` subcommand to `customer-draft` for back-compat.
    if argv and argv[0] == "draft":
        argv = ["customer-draft", *argv[1:]]
    elif argv and argv[0] == "queue":
        # queue command is shared — same path on disk
        pass
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

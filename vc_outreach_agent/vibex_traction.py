"""Live VibeX traction injector for VC outreach drafts.

Why: when you cold-email a VC, "we have 132 makers and 8 projects at
Breakout+" beats "early traction". Pulling the numbers right at draft
time means the email always reflects current state — no stale week-old
numbers in your pipeline.

Cost: $0. Pure SQL through Supabase Management API.

Auth: SUPABASE_PERSONAL_ACCESS_TOKEN + VIBEX_PROJECT_REF (or fall back
to SUPABASE_PROJECT_REF for the common one-project case).

Usage:
    from .models import Project
    from .vibex_traction import inject_vibex_traction

    proj = Project(name="VibeXForge", one_liner="...", traction=[
        "Backed by N/A — bootstrapped",
        "{vibex_total_creators} makers signed up",
        "{vibex_total_projects} projects forged · {vibex_elite_count} at Breakout+",
        "{vibex_total_plays} plays in last 30 days",
    ])
    proj = inject_vibex_traction(proj)  # placeholders → real numbers

The placeholders get expanded into the traction list. Lines whose template
fails to resolve (e.g. SQL fails) are dropped with no error — graceful
degrade keeps the rest of the draft running.
"""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Optional

from .models import Project


VIBEX_TRACTION_SQL = """
SELECT
  (SELECT count(*) FROM creators)                                AS total_creators,
  (SELECT count(*) FROM projects)                                AS total_projects,
  (SELECT coalesce(sum(plays), 0)::bigint FROM projects)         AS total_plays,
  (SELECT coalesce(sum(upvotes), 0)::bigint FROM projects)       AS total_upvotes,
  (SELECT count(*) FROM projects
     WHERE evolution_stage IN ('Breakout','Legend','Myth'))      AS elite_count,
  (SELECT count(*) FROM projects
     WHERE evolution_stage = 'Myth')                             AS myth_count,
  (SELECT count(*) FROM creators
     WHERE joined_at >= current_date - interval '7 days')        AS new_creators_7d,
  (SELECT count(*) FROM projects
     WHERE created_at >= now() - interval '7 days')              AS new_projects_7d
""".strip()


PLACEHOLDER = re.compile(r"\{(vibex_[a-z_0-9]+)\}")


def fetch_vibex_traction_dict(
    *,
    project_ref: Optional[str] = None,
    token: Optional[str] = None,
) -> dict[str, int]:
    """Return live traction numbers as a flat dict: {placeholder: int_value}.
    Empty dict on any failure — caller decides how to handle.
    """
    token = token or os.getenv("SUPABASE_PERSONAL_ACCESS_TOKEN") or ""
    project_ref = (project_ref or os.getenv("VIBEX_PROJECT_REF")
                    or os.getenv("SUPABASE_PROJECT_REF") or "")
    if not token or not project_ref:
        return {}

    url = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    body = json.dumps({"query": VIBEX_TRACTION_SQL}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                  "Content-Type": "application/json",
                  "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return {}
    except Exception:
        return {}

    rows: list = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("result", "rows", "data"):
            if key in data and isinstance(data[key], list):
                rows = data[key]
                break
    if not rows:
        return {}
    row = rows[0]
    out = {}
    for k, v in row.items():
        try:
            out[f"vibex_{k}"] = int(v or 0)
        except (TypeError, ValueError):
            continue
    return out


def inject_vibex_traction(
    project: Project,
    *,
    traction: Optional[dict[str, int]] = None,
) -> Project:
    """Return a new Project with `{vibex_*}` placeholders in traction[]
    expanded to live numbers. Lines that contain unresolved placeholders
    after substitution are dropped (so a missing metric doesn't end up in
    the email as the literal '{vibex_total_plays}' string).

    `traction` is injectable for tests; in production leave None and the
    function pulls live numbers itself.
    """
    if traction is None:
        traction = fetch_vibex_traction_dict()

    new_lines: list[str] = []
    for line in project.traction:
        if not isinstance(line, str):
            continue
        # Find all placeholders in the line
        placeholders = PLACEHOLDER.findall(line)
        if not placeholders:
            new_lines.append(line)
            continue
        # All placeholders must resolve, else drop the line silently
        resolved = line
        ok = True
        for ph in placeholders:
            if ph not in traction:
                ok = False
                break
            # Format with thousands separator for readability
            value = traction[ph]
            resolved = resolved.replace(
                "{" + ph + "}", f"{value:,}" if isinstance(value, int) else str(value))
        if ok:
            new_lines.append(resolved)

    return replace(project, traction=new_lines)

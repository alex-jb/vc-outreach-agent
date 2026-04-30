"""Investor enrichment from a customer-discovery-agent digest.

Cross-agent integration A3: take a markdown digest produced by
customer-discovery-agent (cluster summaries of maker pain points), and
use it as the source of truth for investors' thesis_hint column. The
intent: "Hey {investor}, I noticed your fund writes about {pain cluster
that hits your portfolio}. Orallexa solves exactly this for {evidence
pulled from the CDA cluster}."

Heuristic enrichment in v0.4 (this module):
  1. Parse the CDA digest's `### <cluster summary>` headers + their
     `**N posts · avg score X**` line to identify top-3 highest-volume
     pain clusters.
  2. For each investor row in the input CSV, if `thesis_hint` is empty
     or marked `[from-cda]`, replace it with: "your fund writes about X"
     where X is the top cluster's summary, lightly adapted.

Smarter enrichment (LLM-driven matching) is v0.5 — needs investor's
public writing as additional input.

Backward compatibility: if the digest can't be parsed (e.g. older CDA
format), enrichment is a no-op — the original CSV is unchanged. Never
breaks the user's pipeline.
"""
from __future__ import annotations
import csv
import io
import re
from pathlib import Path


# ── Parse a CDA digest ─────────────────────────────────────

_CLUSTER_HEADER_RE = re.compile(r"^### (.+?)$", re.MULTILINE)
_STATS_RE = re.compile(r"\*\*(\d+) posts? · avg score ([\d.]+)\*\*")
_QUOTE_RE = re.compile(r"^> (.+?)$", re.MULTILINE)


def parse_digest(digest_text: str) -> list[dict]:
    """Extract clusters from a CDA digest. Returns a list of dicts:
        [{"summary": ..., "n_posts": int, "avg_score": float, "quote": str}]
    sorted by n_posts descending. Empty list if the digest doesn't
    contain a Top Themes section."""
    out: list[dict] = []
    headers = list(_CLUSTER_HEADER_RE.finditer(digest_text))
    for i, m in enumerate(headers):
        summary = m.group(1).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(digest_text)
        chunk = digest_text[start:end]
        stats_m = _STATS_RE.search(chunk)
        if not stats_m:
            continue  # not a cluster section, skip
        n_posts = int(stats_m.group(1))
        avg_score = float(stats_m.group(2))
        quote_m = _QUOTE_RE.search(chunk)
        quote = quote_m.group(1).strip() if quote_m else ""
        out.append({
            "summary": summary,
            "n_posts": n_posts,
            "avg_score": avg_score,
            "quote": quote,
        })
    out.sort(key=lambda c: -c["n_posts"])
    return out


# ── Build thesis_hint from a cluster ───────────────────────

def thesis_hint_from_cluster(cluster: dict) -> str:
    """Render a cluster as a one-line thesis_hint suitable for the
    drafter prompt. Keeps it concise + factual; no hyperbole."""
    summary = cluster["summary"].rstrip(".!?")
    if cluster.get("quote"):
        return f"makers complaining about {summary} (e.g. \"{cluster['quote'][:80]}\")"
    return f"makers complaining about {summary}"


# ── Enrich a CSV ───────────────────────────────────────────

ENRICH_MARKER = "[from-cda]"


def enrich_investors_csv(csv_text: str, *,
                          digest_text: str,
                          top_n_clusters: int = 3) -> tuple[str, int]:
    """Replace empty / marker thesis_hints with a top-cluster pain summary.

    Returns (new_csv_text, count_of_rows_enriched).

    Strategy: rotate through the top N clusters as we walk the rows.
    First investor with empty hint gets cluster #1's summary, second
    gets cluster #2's, etc. (Wrap around past N.) Better than "everyone
    gets the same hint" — keeps each email distinct.
    """
    clusters = parse_digest(digest_text)
    if not clusters:
        return csv_text, 0
    top = clusters[:top_n_clusters]

    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    out_rows = []
    enriched_count = 0
    rotor = 0

    for row in reader:
        existing = (row.get("thesis_hint") or "").strip()
        if not existing or existing == ENRICH_MARKER:
            row["thesis_hint"] = thesis_hint_from_cluster(top[rotor % len(top)])
            rotor += 1
            enriched_count += 1
        out_rows.append(row)

    out_buf = io.StringIO()
    writer = csv.DictWriter(out_buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(out_rows)
    return out_buf.getvalue(), enriched_count


def enrich_csv_file(*, csv_path: str | Path, digest_path: str | Path,
                    out_path: str | Path | None = None,
                    top_n_clusters: int = 3) -> dict[str, int]:
    """File-level wrapper. If `out_path` is None, overwrites `csv_path`.
    Returns {"enriched": N, "rows_total": M}."""
    csv_text = Path(csv_path).read_text(encoding="utf-8")
    digest_text = Path(digest_path).read_text(encoding="utf-8")
    new_csv, count = enrich_investors_csv(
        csv_text,
        digest_text=digest_text,
        top_n_clusters=top_n_clusters,
    )
    target = Path(out_path) if out_path else Path(csv_path)
    target.write_text(new_csv, encoding="utf-8")
    rows_total = sum(1 for _ in csv.DictReader(io.StringIO(csv_text)))
    return {"enriched": count, "rows_total": rows_total}

"""Tests for enricher.py — parse CDA digest + fill thesis_hint column."""
from __future__ import annotations
import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vc_outreach_agent.enricher import (
    parse_digest, thesis_hint_from_cluster,
    enrich_investors_csv, enrich_csv_file,
    ENRICH_MARKER,
)


# ─── parse_digest ─────────────────────────────────────────

SAMPLE_DIGEST = """# Customer Discovery Digest

*Generated: 2026-04-29T12:00:00*
*Window: last 168h · Sources: reddit*
*Pain points scanned: **42** · Clusters: **3***

## Top themes

### Launch tooling friction

**12 posts · avg score 45.0**

> I wish PH had a better preview before going live

Sample posts:
- https://reddit.com/x

### CI/CD slowness

**8 posts · avg score 30.0**

> Vercel build minutes are killing my budget

### Supabase RLS confusion

**5 posts · avg score 22.0**

> Took me 3 hours to figure out why my insert was silently failing

---
"""


def test_parse_digest_returns_clusters_sorted():
    clusters = parse_digest(SAMPLE_DIGEST)
    assert len(clusters) == 3
    # Sorted by n_posts desc
    assert clusters[0]["summary"] == "Launch tooling friction"
    assert clusters[0]["n_posts"] == 12
    assert clusters[1]["summary"] == "CI/CD slowness"
    assert clusters[2]["summary"] == "Supabase RLS confusion"


def test_parse_digest_includes_quote():
    clusters = parse_digest(SAMPLE_DIGEST)
    assert "PH had a better preview" in clusters[0]["quote"]


def test_parse_digest_returns_empty_for_garbage():
    assert parse_digest("not a digest at all") == []


def test_parse_digest_returns_empty_for_empty_themes():
    """Headers without stats lines are skipped."""
    bad = "# Header\n\n### Just a header\n\n## More\n"
    assert parse_digest(bad) == []


# ─── thesis_hint_from_cluster ─────────────────────────────

def test_thesis_hint_with_quote():
    cluster = {
        "summary": "Launch tooling friction",
        "n_posts": 12, "avg_score": 45.0,
        "quote": "I wish PH had a better preview",
    }
    hint = thesis_hint_from_cluster(cluster)
    assert "Launch tooling friction" in hint
    assert "PH had a better preview" in hint


def test_thesis_hint_without_quote():
    cluster = {
        "summary": "CI slowness",
        "n_posts": 8, "avg_score": 30.0, "quote": "",
    }
    hint = thesis_hint_from_cluster(cluster)
    assert "CI slowness" in hint


def test_thesis_hint_strips_trailing_punctuation():
    cluster = {"summary": "Pain.", "n_posts": 1, "avg_score": 1.0, "quote": ""}
    hint = thesis_hint_from_cluster(cluster)
    # No double period
    assert hint.count(".") <= 1


# ─── enrich_investors_csv ─────────────────────────────────

CSV_HEADER = "name,email,firm,role,thesis_hint\n"


def test_enrich_fills_empty_thesis_hint():
    csv_text = CSV_HEADER + "Garry,g@y.com,YC,Partner,\nSarah,s@s.com,SF,Principal,\n"
    new_csv, count = enrich_investors_csv(csv_text, digest_text=SAMPLE_DIGEST)
    assert count == 2
    rows = list(csv.DictReader(io.StringIO(new_csv)))
    # Both got hints; rotor means they're different clusters
    assert rows[0]["thesis_hint"] != ""
    assert rows[1]["thesis_hint"] != ""
    assert rows[0]["thesis_hint"] != rows[1]["thesis_hint"]


def test_enrich_skips_rows_with_existing_hints():
    csv_text = (CSV_HEADER
                + "Garry,g@y.com,YC,Partner,already has thesis\n"
                + "Sarah,s@s.com,SF,Principal,\n")
    new_csv, count = enrich_investors_csv(csv_text, digest_text=SAMPLE_DIGEST)
    assert count == 1
    rows = list(csv.DictReader(io.StringIO(new_csv)))
    assert rows[0]["thesis_hint"] == "already has thesis"
    assert rows[1]["thesis_hint"] != ""


def test_enrich_marker_is_replaced():
    csv_text = CSV_HEADER + f"Garry,g@y.com,YC,Partner,{ENRICH_MARKER}\n"
    new_csv, count = enrich_investors_csv(csv_text, digest_text=SAMPLE_DIGEST)
    assert count == 1
    rows = list(csv.DictReader(io.StringIO(new_csv)))
    assert ENRICH_MARKER not in rows[0]["thesis_hint"]
    assert "Launch tooling" in rows[0]["thesis_hint"]


def test_enrich_no_op_when_digest_empty():
    csv_text = CSV_HEADER + "G,g@x.com,YC,P,\n"
    new_csv, count = enrich_investors_csv(csv_text, digest_text="garbage")
    assert count == 0
    assert new_csv == csv_text or new_csv == csv_text  # unchanged content


def test_enrich_rotates_through_top_n_clusters():
    """5 investors, 3 clusters → cluster sequence is c1, c2, c3, c1, c2."""
    rows = [f"Inv{i},i{i}@x.com,F,P,\n" for i in range(5)]
    csv_text = CSV_HEADER + "".join(rows)
    new_csv, count = enrich_investors_csv(
        csv_text, digest_text=SAMPLE_DIGEST, top_n_clusters=3)
    assert count == 5
    parsed = list(csv.DictReader(io.StringIO(new_csv)))
    # Row 0 and row 3 should share a cluster (rotor wraps)
    assert parsed[0]["thesis_hint"] == parsed[3]["thesis_hint"]
    # Row 0 and row 1 should differ
    assert parsed[0]["thesis_hint"] != parsed[1]["thesis_hint"]


# ─── enrich_csv_file ──────────────────────────────────────

def test_enrich_csv_file_overwrites_in_place(tmp_path):
    csv_path = tmp_path / "investors.csv"
    csv_path.write_text(CSV_HEADER + "G,g@x.com,YC,P,\n", encoding="utf-8")
    digest_path = tmp_path / "digest.md"
    digest_path.write_text(SAMPLE_DIGEST, encoding="utf-8")

    summary = enrich_csv_file(csv_path=csv_path, digest_path=digest_path)
    assert summary["enriched"] == 1
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text())))
    assert rows[0]["thesis_hint"] != ""


def test_enrich_csv_file_writes_to_out_path(tmp_path):
    csv_path = tmp_path / "investors.csv"
    csv_path.write_text(CSV_HEADER + "G,g@x.com,YC,P,\n", encoding="utf-8")
    out_path = tmp_path / "investors.enriched.csv"
    digest_path = tmp_path / "digest.md"
    digest_path.write_text(SAMPLE_DIGEST, encoding="utf-8")

    enrich_csv_file(csv_path=csv_path, digest_path=digest_path, out_path=out_path)
    assert out_path.exists()
    # Original NOT overwritten
    assert "thesis_hint:," not in csv_path.read_text()  # original untouched

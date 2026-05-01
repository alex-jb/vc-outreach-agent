"""Tests for VibeX traction injector."""
from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vc_outreach_agent.models import Project
from vc_outreach_agent.vibex_traction import (
    fetch_vibex_traction_dict,
    inject_vibex_traction,
)


def _fake_urlopen(payload):
    fake = MagicMock()
    fake.read.return_value = json.dumps(payload).encode()
    fake.__enter__ = lambda s: s
    fake.__exit__ = lambda *a: None
    return fake


def test_fetch_unconfigured_returns_empty(monkeypatch):
    monkeypatch.delenv("SUPABASE_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("VIBEX_PROJECT_REF", raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    assert fetch_vibex_traction_dict() == {}


def test_fetch_returns_prefixed_keys(monkeypatch):
    monkeypatch.setenv("SUPABASE_PERSONAL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("VIBEX_PROJECT_REF", "abc")
    fake = _fake_urlopen([{
        "total_creators": 132, "total_projects": 87,
        "total_plays": 1247, "total_upvotes": 320,
        "elite_count": 8, "myth_count": 1,
        "new_creators_7d": 14, "new_projects_7d": 8,
    }])
    with patch("urllib.request.urlopen", return_value=fake):
        out = fetch_vibex_traction_dict()
    assert out["vibex_total_creators"] == 132
    assert out["vibex_elite_count"] == 8
    # Output keys are all `vibex_*` prefixed
    assert all(k.startswith("vibex_") for k in out)


def test_fetch_handles_dict_response(monkeypatch):
    monkeypatch.setenv("SUPABASE_PERSONAL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("VIBEX_PROJECT_REF", "abc")
    fake = _fake_urlopen({"result": [{"total_creators": 5}]})
    with patch("urllib.request.urlopen", return_value=fake):
        out = fetch_vibex_traction_dict()
    assert out["vibex_total_creators"] == 5


def test_fetch_swallows_network_errors(monkeypatch):
    monkeypatch.setenv("SUPABASE_PERSONAL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("VIBEX_PROJECT_REF", "abc")
    with patch("urllib.request.urlopen", side_effect=Exception("net")):
        assert fetch_vibex_traction_dict() == {}


def test_inject_expands_placeholders():
    proj = Project(
        name="VibeXForge",
        one_liner="AI launch platform",
        traction=[
            "Bootstrapped solo",
            "{vibex_total_creators} makers signed up",
            "{vibex_total_projects} projects forged · {vibex_elite_count} at Breakout+",
        ],
    )
    out = inject_vibex_traction(proj, traction={
        "vibex_total_creators": 132,
        "vibex_total_projects": 87,
        "vibex_elite_count": 8,
    })
    assert out.traction == [
        "Bootstrapped solo",
        "132 makers signed up",
        "87 projects forged · 8 at Breakout+",
    ]


def test_inject_drops_lines_with_unresolved_placeholder():
    """If a placeholder isn't in traction dict, drop the line — don't ship
    the literal '{vibex_foo}' string in a VC's email."""
    proj = Project(
        name="VibeXForge",
        one_liner="...",
        traction=[
            "Static line — keep",
            "{vibex_missing_metric} something",  # missing → dropped
            "{vibex_total_creators} makers",     # resolves → kept
        ],
    )
    out = inject_vibex_traction(proj, traction={"vibex_total_creators": 50})
    assert "Static line — keep" in out.traction
    assert "50 makers" in out.traction
    assert not any("{vibex_" in line for line in out.traction)
    assert not any("missing_metric" in line for line in out.traction)


def test_inject_thousands_separator():
    proj = Project(name="V", one_liner="x", traction=[
        "{vibex_total_plays} plays",
    ])
    out = inject_vibex_traction(proj, traction={"vibex_total_plays": 12345})
    assert out.traction == ["12,345 plays"]


def test_inject_no_traction_arg_uses_live_fetch(monkeypatch):
    """Production code path: no `traction=` arg → calls fetch_vibex_traction_dict.
    With env unconfigured, fetch returns {}, so all placeholder lines drop
    but static lines survive."""
    monkeypatch.delenv("SUPABASE_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("VIBEX_PROJECT_REF", raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    proj = Project(name="V", one_liner="x", traction=[
        "Static line",
        "{vibex_total_creators} makers",
    ])
    out = inject_vibex_traction(proj)
    assert out.traction == ["Static line"]

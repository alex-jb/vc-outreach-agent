"""Tests for the vc-outreach MCP server tools."""
from __future__ import annotations
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

mcp_available = True
try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
except ImportError:
    mcp_available = False

pytestmark = pytest.mark.skipif(not mcp_available,
                                  reason="mcp optional dep not installed")


@pytest.fixture
def mod():
    from vc_outreach_agent import mcp_server
    return mcp_server


def test_draft_email_no_api_key_uses_template(mod, monkeypatch):
    """Without ANTHROPIC_API_KEY, drafter falls back to template path —
    still returns a draft with subject + body."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = mod.draft_email(
        investor_name="Alice",
        investor_email="alice@vc.com",
        project_name="Orallexa",
        one_liner="AI quant trading agent",
        traction=["Sharpe 1.41"],
    )
    assert "alice@vc.com" in out
    assert "Subject:" in out
    # Body should mention the project somewhere
    assert "Orallexa" in out


def test_list_pending_empty(mod, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    out = mod.list_pending()
    assert "No drafts pending" in out


def test_list_approved_empty(mod, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    out = mod.list_approved()
    assert "No approved drafts" in out


def test_main_skips_when_skip_env_set(mod, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_SKIP", "1")
    with patch.object(mod.mcp, "run") as fake_run:
        mod.main()
    fake_run.assert_not_called()


def test_mcp_instance_is_fastmcp(mod):
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mod.mcp, FastMCP)

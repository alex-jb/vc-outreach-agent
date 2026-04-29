"""Tests for drafter — template fallback + LLM happy path + edge cases.

v0.3+: drafter goes through solo_founder_os.AnthropicClient. Tests inject
a pre-loaded client to avoid re-importing the SDK during tests.
"""
from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vc_outreach_agent.drafter import draft_email
from vc_outreach_agent.models import Investor, Project
from solo_founder_os.anthropic_client import AnthropicClient
from solo_founder_os.testing import fake_anthropic, fake_anthropic_raises


def _inv():
    return Investor(
        name="Garry Tan",
        email="garry@yc.com",
        firm="YC",
        role="Partner",
        thesis_hint="writes about solo-founder agent OS",
    )


def _proj():
    return Project(
        name="Orallexa",
        one_liner="AI-powered quant trading agent",
        traction=["Sharpe 1.41 over 698 backtests",
                  "DSPy pipeline shipped 2026-04"],
        stage="pre-seed",
        raise_amount="$500k",
        deck_url="https://orallexa.com/deck.pdf",
        founder_name="Alex Ji",
        founder_email="alex@orallexa.com",
        why_now="LLMs commoditize signal — execution is the moat now.",
    )


def _client_with_fake(monkeypatch, fake_sdk_client) -> AnthropicClient:
    """Build an AnthropicClient pre-loaded with a mocked SDK client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = AnthropicClient(usage_log_path=None)
    c._client = fake_sdk_client
    return c


# ─── template fallback ──────────────────────────────────────────

def test_template_fallback_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = draft_email(_inv(), _proj())
    assert d.investor_email == "garry@yc.com"
    assert "Orallexa" in d.subject or "Orallexa" in d.body
    assert "Garry" in d.body
    assert "Alex Ji" in d.body
    assert "(template mode" in d.raw_prompt


def test_template_uses_thesis_hint(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = draft_email(_inv(), _proj())
    assert "solo-founder agent OS" in d.body


def test_template_falls_back_when_no_thesis_hint(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    inv = _inv()
    inv.thesis_hint = ""
    d = draft_email(inv, _proj())
    assert "your work at YC" in d.body


# ─── LLM happy path ─────────────────────────────────────────────

def test_llm_path_parses_json(monkeypatch):
    fake = fake_anthropic(json.dumps({
        "subject": "Orallexa — Sharpe 1.41",
        "body": "Hi Garry,\\n\\nLooks like a fit.",
    }))
    client = _client_with_fake(monkeypatch, fake)
    d = draft_email(_inv(), _proj(), client=client)
    assert d.subject == "Orallexa — Sharpe 1.41"
    assert "Hi Garry" in d.body


def test_llm_path_strips_markdown_fence(monkeypatch):
    fake = fake_anthropic('```json\n{"subject":"X","body":"Y"}\n```')
    client = _client_with_fake(monkeypatch, fake)
    d = draft_email(_inv(), _proj(), client=client)
    assert d.subject == "X"
    assert d.body == "Y"


def test_llm_unparseable_falls_back_to_template(monkeypatch):
    fake = fake_anthropic("hello not even json")
    client = _client_with_fake(monkeypatch, fake)
    d = draft_email(_inv(), _proj(), client=client)
    assert "Alex Ji" in d.body
    assert "unparseable" in d.raw_response


def test_llm_exception_falls_back_to_template(monkeypatch):
    fake = fake_anthropic_raises(Exception("network down"))
    client = _client_with_fake(monkeypatch, fake)
    d = draft_email(_inv(), _proj(), client=client)
    assert "Alex Ji" in d.body
    assert "LLM error" in d.raw_response
    assert "network down" in d.raw_response

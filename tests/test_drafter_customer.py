"""Tests for customer-mode drafter (merged from customer-outreach-agent v0.2.0
in vc-outreach-agent v0.9.0).

Same shape as the original customer-outreach test suite, adapted to:
  - import from `vc_outreach_agent.drafter.draft_email_customer`
  - use `CustomerProject` (renamed from `Project` to disambiguate from VC)
  - check `target_email` / `lead_email` aliases on the merged `Draft` shape
  - assert `mode == "customer"` is set on returned Draft
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock

from vc_outreach_agent.drafter import draft_email_customer
from vc_outreach_agent.models import CustomerProject, Lead


def _lead(*, signal: str = "tweeted: tired of launch boards that disappear") -> Lead:
    return Lead(
        email="alice@example.com",
        signal_source="x.com/alice/status/123",
        signal_text=signal,
        name="Alice",
        handle="@alice",
    )


def _proj() -> CustomerProject:
    return CustomerProject(
        name="VibeXForge",
        one_liner="Distribution amplifier for solo AI creators.",
        differentiator="17 platform-native posts in 10s, EN↔ZH native.",
        free_offer="Free for the first 100 creators.",
        paid_tier="$14/month after.",
        founder_name="Alex",
        founder_email="alex@vibexforge.com",
    )


def _fake_client(
    *,
    configured: bool = True,
    subject: str = "Saw your launch-board tweet",
    body: str = "Hey Alice — that exact frustration is what I built X for.",
    err: str | None = None,
):
    c = MagicMock()
    c.configured = configured
    if err:
        c.messages_create_json.return_value = (None, err)
    else:
        c.messages_create_json.return_value = (
            {"subject": subject, "body": body},
            None,
        )
    return c


def test_customer_draft_unconfigured_uses_template():
    fake = _fake_client(configured=False)
    d = draft_email_customer(_lead(), _proj(), client=fake)
    # Template open is "Saw this — \"<signal>\""
    assert "tired of launch boards" in d.body
    assert "Alice" in d.body
    assert d.target_email == "alice@example.com"
    assert d.lead_email == "alice@example.com"  # back-compat alias
    assert d.mode == "customer"
    assert fake.messages_create_json.call_count == 0


def test_customer_draft_uses_claude_subject_body():
    fake = _fake_client()
    d = draft_email_customer(_lead(), _proj(), client=fake)
    assert d.subject == "Saw your launch-board tweet"
    assert "Alice" in d.body
    assert "X for" in d.body
    assert d.mode == "customer"


def test_customer_draft_anthropic_error_falls_back():
    fake = _fake_client(err="rate limit")
    d = draft_email_customer(_lead(), _proj(), client=fake)
    assert "tired of launch boards" in d.body
    assert "fell back" in d.raw_response
    assert d.mode == "customer"


def test_customer_draft_empty_subject_falls_back():
    fake = _fake_client(subject="", body="real body")
    d = draft_email_customer(_lead(), _proj(), client=fake)
    assert "tired of launch boards" in d.body  # template signal


def test_customer_draft_carries_lead_metadata():
    fake = _fake_client()
    d = draft_email_customer(_lead(), _proj(), client=fake)
    assert d.target_email == "alice@example.com"
    assert d.lead_name == "Alice"  # back-compat alias
    assert d.target_name == "Alice"
    assert d.project_name == "VibeXForge"


def test_customer_draft_template_no_name():
    """Lead without name → template uses 'Hey there' instead of 'Hey Alice'."""
    fake = _fake_client(configured=False)
    lead = Lead(
        email="x@y.com",
        signal_source="src",
        signal_text="said something",
        name="",
    )
    d = draft_email_customer(lead, _proj(), client=fake)
    assert "there" in d.body


def test_customer_draft_refuses_empty_signal():
    """signal_text gate: customer mode hard-fails on empty signal — generic
    outbound to cold lists is the wrong audience for this path."""
    lead = Lead(email="x@y.com", signal_source="src", signal_text="")
    with pytest.raises(ValueError, match="signal_text is empty"):
        draft_email_customer(lead, _proj())


def test_customer_draft_refuses_whitespace_signal():
    """signal_text with only whitespace also fails the gate."""
    lead = Lead(email="x@y.com", signal_source="src", signal_text="   \n  ")
    with pytest.raises(ValueError, match="signal_text is empty"):
        draft_email_customer(lead, _proj())

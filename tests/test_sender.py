"""Tests for sender.py — frontmatter parse, send_one, send_approved_queue."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vc_outreach_agent.sender import (
    _parse_frontmatter,
    _extract_section,
    send_one,
    send_approved_queue,
)


# Shared fixture: redirect VC_OUTREACH_QUEUE to tmp_path so tests don't touch
# ~/.vc-outreach-agent/queue
@pytest.fixture(autouse=True)
def _redirect_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))


def _approved_draft(tmp_path, *, body="Hi, please reply.\n\nThanks.",
                    investor_email="x@y.com", subject="Hi"):
    """Write a fake approved draft and return its path."""
    qroot = tmp_path / "queue" / "approved"
    qroot.mkdir(parents=True, exist_ok=True)
    path = qroot / "20260430T100000-orallexa-to-x.md"
    path.write_text(f"""---
project: orallexa
investor_name: X
investor_email: {investor_email}
subject: {subject}
status: approved
drafted_at: 2026-04-30T10:00:00Z
---

# Subject
{subject}

# Body
{body}

---
""")
    return path


# ─── frontmatter / section parsers ────────────────────────────

def test_parse_frontmatter_returns_dict():
    md = "---\nfoo: bar\nbaz: qux\n---\nbody"
    fm = _parse_frontmatter(md)
    assert fm == {"foo": "bar", "baz": "qux"}


def test_parse_frontmatter_missing_returns_empty_dict():
    assert _parse_frontmatter("no frontmatter here") == {}


def test_extract_section_returns_body():
    md = "# Subject\nHello\n\n# Body\nWorld\n"
    assert _extract_section(md, "Subject") == "Hello"
    assert _extract_section(md, "Body") == "World"


# ─── send_one ────────────────────────────────────────────────

def test_send_one_missing_smtp_env(tmp_path, monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    path = _approved_draft(tmp_path)
    ok, reason = send_one(path)
    assert ok is False
    assert "SMTP env vars" in reason


def test_send_one_dry_run_skips_smtp(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    path = _approved_draft(tmp_path)
    with patch("smtplib.SMTP") as smtp:
        ok, reason = send_one(path, dry_run=True)
    assert ok is True
    assert "dry-run OK" in reason
    smtp.assert_not_called()


def test_send_one_dry_run_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    monkeypatch.setenv("SENDER_DRY_RUN", "1")
    path = _approved_draft(tmp_path)
    with patch("smtplib.SMTP") as smtp:
        ok, _ = send_one(path)
    assert ok is True
    smtp.assert_not_called()


def test_send_one_smtp_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    path = _approved_draft(tmp_path)
    fake_smtp = MagicMock()
    fake_smtp.__enter__ = MagicMock(return_value=fake_smtp)
    fake_smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", return_value=fake_smtp):
        ok, reason = send_one(path)
    assert ok is True
    assert reason == "sent"
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("me@example.com", "secret")
    fake_smtp.send_message.assert_called_once()


def test_send_one_smtp_465_uses_ssl(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.resend.com")
    monkeypatch.setenv("SMTP_USER", "resend")
    monkeypatch.setenv("SMTP_PASSWORD", "re_xxx")
    monkeypatch.setenv("SMTP_FROM", "alex@example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    path = _approved_draft(tmp_path)
    fake_smtp = MagicMock()
    fake_smtp.__enter__ = MagicMock(return_value=fake_smtp)
    fake_smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP_SSL", return_value=fake_smtp) as ssl_smtp, \
         patch("smtplib.SMTP") as plain_smtp:
        ok, reason = send_one(path)
    assert ok is True
    ssl_smtp.assert_called_once()
    plain_smtp.assert_not_called()


def test_send_one_smtp_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    path = _approved_draft(tmp_path)
    with patch("smtplib.SMTP", side_effect=Exception("auth failed")):
        ok, reason = send_one(path)
    assert ok is False
    assert "SMTP error" in reason
    assert "auth failed" in reason


def test_send_one_missing_subject(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "x")
    monkeypatch.setenv("SMTP_USER", "x")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setenv("SMTP_FROM", "x")
    qroot = tmp_path / "queue" / "approved"
    qroot.mkdir(parents=True, exist_ok=True)
    bad = qroot / "missing.md"
    bad.write_text("---\ninvestor_email: x@y.com\n---\n")
    ok, reason = send_one(bad)
    assert ok is False
    assert "missing" in reason


# ─── send_approved_queue ─────────────────────────────────────

def test_send_approved_queue_empty(tmp_path, monkeypatch):
    summary = send_approved_queue()
    assert summary == {"sent": [], "failed": [], "skipped": []}


def test_send_approved_queue_dry_run_moves_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "x")
    monkeypatch.setenv("SMTP_USER", "x")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setenv("SMTP_FROM", "x")
    path = _approved_draft(tmp_path)
    summary = send_approved_queue(dry_run=True)
    assert len(summary["sent"]) == 1
    assert not path.exists()  # moved to sent/
    sent_dir = tmp_path / "queue" / "sent"
    assert any(sent_dir.glob("*.md"))


def test_send_approved_queue_failure_kept_in_approved(tmp_path, monkeypatch):
    """A failed send leaves the file in approved/ for retry/inspection."""
    # No SMTP env → send_one returns failure
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    path = _approved_draft(tmp_path)
    summary = send_approved_queue()
    assert len(summary["failed"]) == 1
    assert path.exists()  # still in approved/

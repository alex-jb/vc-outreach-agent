"""Tests for queue.py — write to pending, list by status."""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vc_outreach_agent.models import Draft


@pytest.fixture(autouse=True)
def _redirect_queue(tmp_path, monkeypatch):
    """Send queue writes to a tmp dir so tests never pollute the real
    ~/.vc-outreach-agent/queue/ on the dev machine."""
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    # Reload module to pick up new env var
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)


def _draft() -> Draft:
    return Draft(
        investor_email="x@y.com",
        investor_name="Garry Tan",
        project_name="orallexa",
        subject="Hi",
        body="One paragraph.",
        drafted_at=datetime.now(timezone.utc),
        raw_prompt="(prompt)",
        raw_response="(response)",
    )


def test_queue_writes_pending_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)
    path = q.queue_draft(_draft())
    assert path.exists()
    assert "pending" in str(path)
    body = path.read_text()
    assert "investor_email: x@y.com" in body
    assert "Hi" in body
    assert "One paragraph." in body


def test_queue_filename_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)
    d = _draft()
    d.investor_name = "First/Name <weird>"
    d.project_name = "weird::name"
    path = q.queue_draft(d)
    # No slashes, brackets, or colons in filename
    assert "/" not in path.name
    assert "<" not in path.name
    assert ":" not in path.name


def test_list_queue_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)
    assert q.list_queue() == []


def test_list_queue_returns_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)
    q.queue_draft(_draft())
    paths = q.list_queue()
    assert len(paths) == 1
    assert paths[0].suffix == ".md"


def test_list_queue_per_status(tmp_path, monkeypatch):
    monkeypatch.setenv("VC_OUTREACH_QUEUE", str(tmp_path / "queue"))
    import importlib
    from vc_outreach_agent import queue as q
    importlib.reload(q)
    q.queue_draft(_draft(), status="approved")
    assert len(q.list_queue(status="approved")) == 1
    assert q.list_queue(status="pending") == []

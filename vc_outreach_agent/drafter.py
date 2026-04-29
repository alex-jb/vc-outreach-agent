"""Draft personalized cold emails per (investor, project) pair via Claude.

Prompt design philosophy:
- Open with one specific line from the investor's thesis_hint that matches
  the project. Never generic ("I follow your work" → BANNED).
- Lead with traction, not vision. Numbers > adjectives.
- 3-4 sentences max. Hyperlink the deck. Ask for a 15-min call.
- Never use the words: "synergy", "disrupting", "passionate", "leverage",
  "innovative", "cutting-edge", "revolutionize". The prompt explicitly
  forbids these.

Graceful degradation: if no ANTHROPIC_API_KEY, returns a template-mode
draft (still personalized via thesis_hint substitution) so the agent stays
useful without a key. Both paths return the same `Draft` shape.

v0.3: LLM call goes through solo_founder_os.AnthropicClient. Token usage
is auto-logged to ~/.vc-outreach-agent/usage.jsonl, where cost-audit-agent
picks it up for monthly spend reports.
"""
from __future__ import annotations
import os
import pathlib
from datetime import datetime, timezone
from typing import Optional

from solo_founder_os.anthropic_client import (
    AnthropicClient,
    DEFAULT_SONNET_MODEL,
)

from .models import Draft, Investor, Project


DEFAULT_MODEL = os.getenv("VC_OUTREACH_MODEL", DEFAULT_SONNET_MODEL)
USAGE_LOG_PATH = (pathlib.Path.home()
                  / ".vc-outreach-agent" / "usage.jsonl")


SYSTEM_PROMPT = """You are an indie founder writing one cold email to one investor.

Rules — break any of these and the email will be rejected by HITL:

1. Open with ONE specific line that ties the investor's known thesis to the
   project. Use the `thesis_hint` field. Never say "I follow your work" or
   "I admire your investments". Never name-drop other portfolio companies
   unless they're directly relevant.

2. Sentences 2-3: lead with TRACTION, never vision. Drop one number, one
   shipped artifact, one signal of demand. Vision is implied by the artifact.

3. Sentence 4: the ask. ONE specific ask. "15-minute call this week" or
   "feedback on this brief deck" — never "any thoughts you have".

4. Length: under 110 words for the body. Under 8 words for the subject.

5. BANNED words/phrases (hard fail): synergy, disrupting, passionate,
   leverage, innovative, cutting-edge, revolutionize, "I'd love to",
   "circle back", "touch base", "thought leader", "in the AI space",
   "exciting opportunity".

6. Tone: peer-to-peer, terse, no exclamation marks, no emojis.

7. End with the founder's name + their email. No corporate signature.

Output format — respond with EXACTLY this JSON, no preamble, no markdown:

{
  "subject": "...",
  "body": "..."
}

Use \\n for line breaks inside body."""


def _build_user_prompt(inv: Investor, proj: Project) -> str:
    traction = "\n".join(f"- {t}" for t in proj.traction) or "(no traction listed)"
    return f"""Project: {proj.name}
One-liner: {proj.one_liner}
Stage / raise: {proj.stage} {f'/ {proj.raise_amount}' if proj.raise_amount else ''}
Traction:
{traction}
Why now: {proj.why_now or '(not specified)'}
Deck: {proj.deck_url or '(not provided)'}

Founder: {proj.founder_name} <{proj.founder_email}>

Investor: {inv.name} ({inv.role} at {inv.firm})
Thesis hint: {inv.thesis_hint or '(none — reference the firm only)'}
Notes: {inv.notes or '(none)'}

Write the email now."""


def _template_fallback(inv: Investor, proj: Project) -> Draft:
    """No-API-key path: a basic template that's at least personalized via
    thesis_hint. Better than nothing, but the LLM path produces much higher
    open rates."""
    subject = f"{proj.name}: {proj.one_liner[:40]}"
    hint = inv.thesis_hint or f"your work at {inv.firm}"
    traction_line = proj.traction[0] if proj.traction else proj.one_liner
    body = (
        f"Hi {inv.name.split()[0]},\n\n"
        f"Saw {hint} — {proj.name} feels relevant.\n\n"
        f"Quick: {traction_line}. {proj.why_now or 'Building this because the alternative is wasted founder time.'}\n\n"
        f"Got 15 minutes this week? Deck: {proj.deck_url or '(send on request)'}\n\n"
        f"— {proj.founder_name}\n{proj.founder_email}"
    )
    return Draft(
        investor_email=inv.email,
        investor_name=inv.name,
        project_name=proj.name,
        subject=subject,
        body=body,
        drafted_at=datetime.now(timezone.utc),
        raw_prompt="(template mode — no API key)",
        raw_response="",
    )


def draft_email(inv: Investor, proj: Project,
                *, model: str = DEFAULT_MODEL,
                client: AnthropicClient | None = None) -> Draft:
    """Draft one email for (investor, project). Always returns a Draft;
    falls back to template mode if Claude is unavailable.

    `client` is injectable for tests. In production, leave it None and
    the function constructs an AnthropicClient pointed at the
    vc-outreach usage log.
    """
    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH)

    if not client.configured:
        return _template_fallback(inv, proj)

    user_prompt = _build_user_prompt(inv, proj)
    resp, err = client.messages_create(
        model=model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if err is not None:
        d = _template_fallback(inv, proj)
        d.raw_response = f"(LLM error, fell back to template: {err})"
        return d

    text = AnthropicClient.extract_text(resp)

    # Parse JSON
    import json
    subject = ""
    body = ""
    try:
        # Trim ```json ... ``` if Claude added it despite the rule
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        obj = json.loads(cleaned)
        subject = obj.get("subject", "").strip()
        body = obj.get("body", "").strip()
    except Exception:
        # Unparseable: fall back to template, keep raw for audit
        d = _template_fallback(inv, proj)
        d.raw_response = f"(unparseable LLM response, fell back: {text[:200]})"
        return d

    return Draft(
        investor_email=inv.email,
        investor_name=inv.name,
        project_name=proj.name,
        subject=subject,
        body=body,
        drafted_at=datetime.now(timezone.utc),
        raw_prompt=user_prompt,
        raw_response=text,
    )

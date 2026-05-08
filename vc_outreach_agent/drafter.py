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

from solo_founder_os.anthropic_client import (
    AnthropicClient,
    DEFAULT_HAIKU_MODEL,
    DEFAULT_SONNET_MODEL,
)

from .models import CustomerProject, Draft, Investor, Lead, Project


DEFAULT_MODEL = os.getenv("VC_OUTREACH_MODEL", DEFAULT_SONNET_MODEL)
USAGE_LOG_PATH = (pathlib.Path.home()
                  / ".vc-outreach-agent" / "usage.jsonl")

# Customer mode (merged in v0.9.0) writes to a separate usage log so
# cost-audit-agent can attribute spend per mode and so the existing
# customer-outreach-agent path through `~/.customer-outreach-agent/`
# (used by older Alex shell history + cron jobs) keeps working.
DEFAULT_MODEL_CUSTOMER = os.getenv("CUSTOMER_OUTREACH_MODEL", DEFAULT_HAIKU_MODEL)
USAGE_LOG_PATH_CUSTOMER = (pathlib.Path.home()
                           / ".customer-outreach-agent" / "usage.jsonl")


def _reflect(reason: str, signal: str) -> None:
    """Log a template-fallback event so future drafts learn from this miss.
    Best-effort; never breaks the drafter's main loop."""
    try:
        from solo_founder_os import log_outcome
        log_outcome(".vc-outreach-agent", task="draft_email",
                    outcome="PARTIAL",
                    signal=f"{reason}: {str(signal)[:200]}")
    except Exception:
        pass


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


DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description":
                    "Email subject. Under 8 words. Plain text, no emoji."},
        "body": {"type": "string", "description":
                 "Email body. Under 110 words. \\n for line breaks."},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def draft_email(inv: Investor, proj: Project,
                *, model: str = DEFAULT_MODEL,
                client: AnthropicClient | None = None,
                inject_traction: bool = True) -> Draft:
    """Draft one email for (investor, project). Always returns a Draft;
    falls back to template mode if Claude is unavailable.

    `client` is injectable for tests. In production, leave it None and
    the function constructs an AnthropicClient pointed at the
    vc-outreach usage log.

    v0.6: uses solo_founder_os.messages_create_json — JSON output is
    schema-guaranteed, eliminates the markdown-fence-stripping +
    try/except parse path that v0.5 had. Template fallback still
    triggers on missing key / network error / API beta hiccup.
    """
    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH)

    # v0.7: inject live VibeX traction into proj.traction[] — any
    # `{vibex_*}` placeholders get expanded with current Supabase numbers.
    # Off-switch: pass inject_traction=False (e.g. when proj isn't VibeX,
    # or when running tests).
    if inject_traction:
        from .vibex_traction import inject_vibex_traction
        proj = inject_vibex_traction(proj)

    if not client.configured:
        return _template_fallback(inv, proj)

    user_prompt = _build_user_prompt(inv, proj)
    obj, err = client.messages_create_json(
        schema=DRAFT_SCHEMA,
        model=model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if err is not None:
        _reflect("LLM error", err)
        d = _template_fallback(inv, proj)
        d.raw_response = f"(LLM error, fell back to template: {err})"
        return d

    subject = (obj.get("subject") or "").strip()
    body = (obj.get("body") or "").strip()
    if not subject or not body:
        _reflect("empty fields", "model returned empty subject or body")
        d = _template_fallback(inv, proj)
        d.raw_response = "(LLM returned empty subject/body, fell back)"
        return d

    # L3 skill library: record this as a successful example.
    # Best-effort import — older solo-founder-os won't have skills module.
    try:
        from solo_founder_os import record_example
        record_example(
            "draft-vc-email",
            inputs={
                "investor_name": inv.name,
                "firm": inv.firm,
                "thesis_hint": inv.thesis_hint,
                "project_name": proj.name,
                "one_liner": proj.one_liner,
                "why_now": proj.why_now,
            },
            output=f"Subject: {subject}\n\n{body}",
            note="LLM-drafted, pre-HITL",
        )
    except Exception:
        pass

    return Draft(
        investor_email=inv.email,
        investor_name=inv.name,
        project_name=proj.name,
        subject=subject,
        body=body,
        drafted_at=datetime.now(timezone.utc),
        raw_prompt=user_prompt,
        raw_response=f"(structured-output JSON: {obj})",
    )


# ═════════════════════════════════════════════════════════════════════════
# Customer mode — merged from customer-outreach-agent v0.2.0 in v0.9.0
# ═════════════════════════════════════════════════════════════════════════
#
# Different from VC mode by design:
#   - Open is the signal that triggered outreach (verbatim quote / observable
#     fact), NOT a thesis hint.
#   - Ask is "try the product on us", reversible + free / cheap. NOT a meeting.
#   - Tone: indie-maker-to-indie-maker. NOT founder-to-investor.
#   - 90 words max body, ≤6 words subject (vs VC's 110 / 8).
#   - Default model: Haiku (volume + cheap), VC uses Sonnet (cold $$ matters).
#   - Reflexion: log_outcome with skip_reflection=True (Haiku-on-Haiku
#     reflection is too expensive in the hot draft path; supervisor backfills
#     offline).
#   - Refuses to draft when signal_text is empty — generic outbound is the
#     wrong audience for this mode; use vc-mode for cold investor lists.

def _log_reflection_customer(outcome: str, signal: str) -> None:
    """L1 reflexion sink for customer mode (skip_reflection=True path)."""
    try:
        from solo_founder_os import log_outcome
        log_outcome(
            ".customer-outreach-agent",
            "draft_customer_outreach_email",
            outcome,
            signal,
            skip_reflection=True,
        )
    except Exception:
        pass


SYSTEM_PROMPT_CUSTOMER = """You are an indie founder writing one personalized cold email \
to a potential customer (not an investor).

Rules — break any of these and the draft is rejected:

1. Open with ONE specific line that quotes or paraphrases the signal that \
made you reach out (their tweet, their post, their comment, etc). Use the \
`signal_text` field verbatim if it's short enough.

2. The product comes second, not first. Don't open with "I'm building X". \
Open with what THEY said.

3. The ASK is "try it free / cheap". Specific offer. NOT "would you take a \
meeting", NOT "happy to chat", NOT "would love to learn more".

4. 90 words max. Subject ≤6 words. No emoji. No exclamation marks. No \
"hope this email finds you well".

5. End with the link to try it. Then sign with first name only.

6. NEVER use these phrases: "circling back", "touching base", "quick \
question", "synergy", "leverage", "ecosystem", "game-changer", "AI-powered" \
(it's already AI; don't oversell), "transform", "revolutionize".

7. If the signal_text mentions a competitor, address it specifically — don't \
hide that you noticed.

Tone reference: someone you'd actually want to hear from, not a sales rep."""


DRAFT_SCHEMA_CUSTOMER = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": ("Email subject. ≤6 words, no emoji, no marketing "
                            "speak. Plain text."),
        },
        "body": {
            "type": "string",
            "description": ("Email body. ≤90 words. Use \\n for line breaks."),
        },
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def _build_user_prompt_customer(lead: Lead, proj: CustomerProject) -> str:
    return f"""Lead:
  Name: {lead.name or '(unknown — start with "Hey")'}
  Email: {lead.email}
  Handle: {lead.handle or '(none)'}
  Signal source: {lead.signal_source}
  Signal text: {lead.signal_text}
  Notes: {lead.notes or '(none)'}

Project:
  Name: {proj.name}
  One-liner: {proj.one_liner}
  Differentiator: {proj.differentiator or '(skip — focus on signal alignment)'}
  Free offer: {proj.free_offer or '(say "free to try, takes 30 seconds")'}
  Paid tier (after free): {proj.paid_tier or '(skip)'}
  Proof URL: {proj.proof_url or '(skip)'}

Founder: {proj.founder_name} <{proj.founder_email}>

Write the email now."""


def _template_fallback_customer(lead: Lead, proj: CustomerProject) -> Draft:
    """No-API-key path for customer mode. Less personalized, but doesn't
    ship 'Dear Sir/Madam' — uses signal_text excerpt as the open."""
    first_name = lead.name.split()[0] if lead.name else "there"
    signal_excerpt = lead.signal_text.strip().split("\n")[0][:120]
    free_line = (proj.free_offer or "Free to try, no signup wall — takes "
                 "30 seconds.")
    subject = proj.name[:30]
    body = (
        f"Hey {first_name},\n\n"
        f"Saw this — \"{signal_excerpt}\".\n\n"
        f"{proj.name}: {proj.one_liner}\n\n"
        f"{free_line} If it's not for you, no email follow-up.\n\n"
        f"— {proj.founder_name.split()[0] if proj.founder_name else 'me'}"
    )
    return Draft(
        investor_email=lead.email,
        investor_name=lead.name,
        project_name=proj.name,
        subject=subject,
        body=body,
        mode="customer",
        drafted_at=datetime.now(timezone.utc),
        raw_prompt="(template mode — no API key)",
        raw_response="",
    )


def draft_email_customer(
    lead: Lead,
    proj: CustomerProject,
    *,
    model: str = DEFAULT_MODEL_CUSTOMER,
    client: AnthropicClient | None = None,
) -> Draft:
    """Draft one customer-mode cold email. Always returns a Draft.

    Refuses (raises ValueError) when signal_text is empty — generic outbound
    to cold lists is the wrong audience for this path; use draft_email() with
    a cold-investor list instead.
    """
    if not lead.signal_text or not lead.signal_text.strip():
        raise ValueError(
            "Refusing to draft customer-mode email — signal_text is empty. "
            "Customer-mode outreach requires a verbatim observable signal "
            "(tweet, comment, post). For thesis-driven cold outreach use "
            "draft_email() (vc mode)."
        )

    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH_CUSTOMER)

    if not client.configured:
        return _template_fallback_customer(lead, proj)

    user_prompt = _build_user_prompt_customer(lead, proj)
    obj, err = client.messages_create_json(
        schema=DRAFT_SCHEMA_CUSTOMER,
        model=model,
        max_tokens=500,
        system=SYSTEM_PROMPT_CUSTOMER,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if err is not None:
        _log_reflection_customer("PARTIAL", f"draft Claude error: {str(err)[:200]}")
        d = _template_fallback_customer(lead, proj)
        d.raw_response = f"(LLM error, fell back to template: {err})"
        return d

    subject = (obj.get("subject") or "").strip()
    body = (obj.get("body") or "").strip()
    if not subject or not body:
        _log_reflection_customer(
            "PARTIAL",
            "Claude returned empty subject or body — fell back to template",
        )
        d = _template_fallback_customer(lead, proj)
        d.raw_response = "(LLM returned empty subject/body, fell back)"
        return d

    # L3 skill library — separate skill name so distill_skill can derive
    # a customer-specific learned template independent of the VC one.
    try:
        from solo_founder_os import record_example
        record_example(
            "draft-customer-outreach",
            inputs={
                "lead_name": lead.name,
                "signal_source": lead.signal_source,
                "signal_text": lead.signal_text[:300],
                "project_name": proj.name,
                "one_liner": proj.one_liner,
                "free_offer": proj.free_offer,
            },
            output=f"Subject: {subject}\n\n{body}",
            note="LLM-drafted, pre-HITL",
        )
    except Exception:
        pass

    return Draft(
        investor_email=lead.email,
        investor_name=lead.name,
        project_name=proj.name,
        subject=subject,
        body=body,
        mode="customer",
        drafted_at=datetime.now(timezone.utc),
        raw_prompt=user_prompt,
        raw_response=f"(structured-output JSON: {obj})",
    )

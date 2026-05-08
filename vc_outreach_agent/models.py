"""Data classes for both VC and customer outreach modes (v0.9.0 merged release).

Original VC types: Investor, Project, Draft (unchanged for back-compat).
Customer types added in v0.9.0: Lead, CustomerProject. Both modes share `Draft`.

A `Draft.mode` field discriminates which target produced it; sender and queue
code dispatches on that field. Field names retain `investor_*` for v0.x
back-compat — when `mode=="customer"`, `investor_email` is just the lead's
email. Migration to mode-neutral names planned for v2.0.0.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Union


# ---------------------------------------------------------------------------
# VC mode (unchanged from v0.8.0)
# ---------------------------------------------------------------------------

@dataclass
class Investor:
    """One investor target. The minimum viable record is name + email +
    one reason to think they'd care (thesis_hint)."""
    name: str
    email: str
    firm: str = ""
    role: str = ""                  # "Partner", "Principal", "Scout", etc.
    thesis_hint: str = ""           # "writes about agent infra" / "led X round"
    linkedin: str = ""
    twitter: str = ""
    notes: str = ""
    last_contacted: Optional[datetime] = None


@dataclass
class Project:
    """The project being pitched. Used to prime the email-drafting prompt
    with concrete numbers + traction.

    Note: also aliased as `VcProject` in v0.9.0 to clarify intent in
    customer-mode codepaths."""
    name: str                       # "Orallexa"
    one_liner: str                  # "AI-powered quant trading agent"
    traction: list[str] = field(default_factory=list)
                                    # ["Sharpe 1.41 over 698 backtests",
                                    #  "DSPy-based pipeline shipped 2026-04",
                                    #  "Used by 5 paying users"]
    stage: str = ""                 # "pre-seed", "seed", "Series A"
    raise_amount: str = ""          # "$500k"
    deck_url: str = ""              # link to pitch deck (Notion/PDF)
    founder_name: str = ""
    founder_email: str = ""
    why_now: str = ""               # one-line market timing


# Alias for clarity in customer-mode contexts.
VcProject = Project


# ---------------------------------------------------------------------------
# Customer mode (merged from customer-outreach-agent v0.2.0 in 2026-05-08)
# ---------------------------------------------------------------------------

@dataclass
class Lead:
    """One potential customer.

    The minimum viable record is email + signal — concrete observable
    behavior that tells you THIS person might want THIS product.

      Lead(
          email="alice@x.com",
          name="Alice",
          signal_source="x.com/alice/status/...",
          signal_text="tweeted: 'tired of launch boards that don't track \
            evolution over time'",
          handle="@alice",
      )

    `signal_text` is the open of every customer-mode outreach email —
    verbatim. The CLI + draft_email() refuse to produce a draft when
    signal_text is empty. Generic outbound to cold lists is the wrong
    audience for this agent; use vc-mode for those.
    """
    email: str
    signal_source: str              # URL or "PH comment on vibex" etc
    signal_text: str                # the verbatim observation
    name: str = ""
    handle: str = ""                # @handle on X, IH username, etc
    notes: str = ""
    last_contacted: Optional[datetime] = None


@dataclass
class CustomerProject:
    """The project being sold to customers (NOT investors).

    Customer-facing wording: differentiator + free offer + paid tier +
    proof URL. No traction list or raise size — those are investor-rhetoric
    fields that don't translate to customer-mode emails."""
    name: str
    one_liner: str
    differentiator: str = ""        # what makes THIS product not generic
    free_offer: str = ""            # "free for 14 days", "free for first 100"
    paid_tier: str = ""             # "$5/month after", "$3 one-time"
    proof_url: str = ""             # social proof link (a real success story)
    founder_name: str = ""
    founder_email: str = ""


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

Mode = Literal["vc", "customer"]
Target = Union[Investor, Lead]
ProjectAny = Union[Project, CustomerProject]


@dataclass
class Draft:
    """Output of the drafter — one personalized email.

    Field name `investor_email` retained from v0.8.0 for back-compat — in
    customer mode, it's the lead's email. The `mode` field discriminates."""
    investor_email: str
    subject: str
    body: str
    investor_name: str = ""
    project_name: str = ""
    mode: Mode = "vc"
    drafted_at: Optional[datetime] = None
    raw_prompt: str = ""             # for audit trail in queue/
    raw_response: str = ""

    # ---- mode-neutral aliases (read-only) ----
    @property
    def target_email(self) -> str:
        return self.investor_email

    @property
    def target_name(self) -> str:
        return self.investor_name

    # ---- customer-mode aliases (read-only) ----
    @property
    def lead_email(self) -> str:
        return self.investor_email

    @property
    def lead_name(self) -> str:
        return self.investor_name

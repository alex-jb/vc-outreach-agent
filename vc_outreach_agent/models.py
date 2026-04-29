"""Data classes shared across the agent: Investor, Project, Draft."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    with concrete numbers + traction."""
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


@dataclass
class Draft:
    """Output of the drafter — one personalized email for (investor, project)."""
    investor_email: str
    subject: str
    body: str
    investor_name: str = ""
    project_name: str = ""
    drafted_at: Optional[datetime] = None
    raw_prompt: str = ""            # for audit trail in queue/
    raw_response: str = ""

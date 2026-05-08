"""vc-outreach-agent — find investors AND paying customers, draft personalized
cold emails, manage replies via a markdown HITL queue. Solo Founder OS agent #3.

v0.9.0 (2026-05-08) merges the previously-separate `customer-outreach-agent`
into this package as `--mode=customer`. The original VC mode is unchanged
and remains the default. Customer mode is for warm signal-driven outbound to
paying customers — different prompt, different default model (Haiku vs Sonnet),
different recipient validation (signal_text required), separate queue root,
separate usage log for cost-audit attribution.

NEVER auto-sends. v0.1+ always queues for human approval.
"""
__version__ = "0.9.0"

from .drafter import (
    draft_email,           # vc mode (Investor + Project)
    draft_email_customer,  # customer mode (Lead + CustomerProject)
)
from .models import (
    CustomerProject,
    Draft,
    Investor,
    Lead,
    Project,
    VcProject,
)

__all__ = [
    "__version__",
    "draft_email",
    "draft_email_customer",
    "Investor",
    "Lead",
    "Project",
    "VcProject",
    "CustomerProject",
    "Draft",
]

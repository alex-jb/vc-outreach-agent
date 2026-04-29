"""vc-outreach-agent — find investors, draft personalized cold emails,
manage replies. Solo Founder OS agent #3.

Designed for indie / pre-seed founders raising on a story they can defend.
The first version is intentionally minimal: a CLI that takes a project pitch
+ a list of investors, drafts personalized emails per (investor, project)
pair via Claude, queues them into a markdown HITL inbox for human review,
and tracks who said yes / no / didn't reply.

NEVER auto-sends. v0.1 always queues for human approval. v0.5+ may add
auto-send for low-stakes follow-ups, but cold first emails always go
through HITL.
"""
__version__ = "0.3.0"

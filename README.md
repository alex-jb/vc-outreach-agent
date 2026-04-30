# vc-outreach-agent

**English** | [中文](README.zh-CN.md)

> Solo Founder OS agent #3 — finds investors, drafts personalized cold emails per (investor, project) pair via Claude, manages replies via a markdown HITL queue. Never auto-sends. Always your edit, your hit-send.

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/vc-outreach-agent.svg)](https://pypi.org/project/vc-outreach-agent/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#)
[![Model](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?logoColor=white)](https://anthropic.com)

Built by [Alex Ji](https://github.com/alex-jb) — solo founder shipping [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) and [VibeXForge](https://github.com/alex-jb/vibex). Born from this thought:

> *I have 50 investor names in a spreadsheet. Hand-writing 50 personalized cold emails takes 10 hours. Sending the same templated email 50 times gets 0 replies. There has to be a better default.*

## What it does

```
investors.csv  +  project.yml
                  ↓
              Claude (Sonnet 4.6, prompt enforces no-bullshit constraints)
                  ↓
              queue/pending/<timestamp>-<project>-to-<investor>.md
                  ↓
        ┌────────────────────────────────┐
        │  Human review in Obsidian      │
        │  (edit / approve / reject)      │
        └────────────────────────────────┘
                  ↓
              queue/approved/  →  v0.2 SMTP sender
              queue/rejected/  →  archived, no send
```

The drafter prompt enforces these rules — anything else gets parsed-and-fallback to a template:

1. Open with ONE specific line tying the investor's thesis to the project. No "I follow your work" filler.
2. Sentences 2-3 lead with **traction**, not vision. One number, one shipped artifact, one demand signal.
3. Sentence 4: ONE specific ask. "15-min call this week" — never "any thoughts you have".
4. Body under 110 words. Subject under 8 words.
5. **Banned vocabulary** (hard fail): synergy, disrupting, passionate, leverage, innovative, cutting-edge, revolutionize, "I'd love to", "circle back", "touch base", "thought leader", "in the AI space", "exciting opportunity".
6. Tone: peer-to-peer, terse, no exclamation marks, no emojis.

## Install

```bash
git clone https://github.com/alex-jb/vc-outreach-agent.git
cd vc-outreach-agent
pip install -e .
cp .env.example .env  # fill in ANTHROPIC_API_KEY
```

## Usage

```bash
# 1. Describe your project once
cat > orallexa.yml <<EOF
name: Orallexa
one_liner: AI-powered quant trading agent
stage: pre-seed
raise_amount: \$500k
deck_url: https://orallexa.com/deck.pdf
founder_name: Alex Ji
founder_email: alex@orallexa.com
why_now: LLMs commoditize signal — execution is the moat now.
traction:
  - Sharpe 1.41 over 698 backtests
  - DSPy pipeline shipped 2026-04
EOF

# 2. List investors in a CSV (columns: name,email,firm,role,thesis_hint,linkedin,twitter,notes)
# (the thesis_hint column is the key one — that's what makes each email feel personalized)

# 3. Fan-draft into the queue
vc-outreach-agent draft --project orallexa.yml --investors investors.csv

# 4. Review at ~/.vc-outreach-agent/queue/pending/
#    Open each .md in Obsidian, edit if needed, then move to:
#      ../approved/  to send
#      ../rejected/  to skip
```

## Why HITL is non-negotiable for cold outreach

Auto-send for cold investor emails is a category error. Two reasons:

1. **One bad email burns the relationship.** Investors talk to each other. A rude or off-base auto-sent email kills not just this round but next round too.
2. **The 1% of personalization that actually matters comes from your context, not Claude's.** "Hey, I noticed you led the Round at X — I'm going to need exactly that playbook." Claude can't know which investors you've met IRL.

v0.1 is queue-only. v0.2 will add SMTP send for **approved** drafts (still requires you to move the file). v0.5 may add auto-send for low-stakes follow-ups, but cold first emails always go through HITL.

## Roadmap

- [x] **v0.1** — Drafter (LLM + template fallback) · markdown HITL queue · CSV/YAML input · 14 tests
- [x] **v0.2** — SMTP sender for `queue/approved/` (Gmail/Postmark/Resend/Sendgrid) · dry-run mode · 25 tests
- [ ] **v0.3** — Investor enrichment (Twitter / LinkedIn pull) — auto-build thesis_hint
- [ ] **v0.4** — Multi-touch follow-ups (T+5d, T+12d) with declining conviction
- [ ] **v0.5** — Pipeline analytics: open rate / reply rate / meeting rate by thesis_hint pattern

## MCP server (Claude Desktop / Cursor / Zed)

Draft an investor email inline from your AI assistant.

```bash
pip install 'vc-outreach-agent[mcp]'
```

```json
{
  "mcpServers": {
    "vc-outreach": {
      "command": "vc-outreach-mcp",
      "env": { "ANTHROPIC_API_KEY": "..." }
    }
  }
}
```

Tools: `draft_email(...)` · `list_pending()` · `list_approved()`

## License

MIT.

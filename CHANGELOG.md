# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.9.0] — 2026-05-08

**Merged the deprecated `customer-outreach-agent` into this package as a
second mode.** Solo Founder OS stack collapses 11 → 10 with this release.

### Added
- **`--mode customer` (via `customer-draft` subcommand)** — port of the v0.2.0
  `customer-outreach-agent` flow. Drafts personalized cold emails to paying
  customers from `Lead + CustomerProject` with verbatim `signal_text` open.
- **`customer-outreach-agent` console_script alias** — calls into this
  package's `main_customer()` entry point. Existing shell history / cron
  jobs that invoke `customer-outreach-agent draft --project p.json
  --leads leads.csv` keep working unchanged (legacy `draft` subcommand maps
  to the new `customer-draft` internally).
- **`Lead`** dataclass (`email + signal_source + signal_text + name + handle`).
  Verbatim signal_text is the open of every customer-mode draft. Blank
  signal_text raises `ValueError` from `draft_email_customer()` and the
  CLI drops the row — generic outbound to cold lists is the wrong audience
  for this mode; use vc-mode (`draft` subcommand) for that.
- **`CustomerProject`** dataclass — customer-facing project shape
  (`differentiator + free_offer + paid_tier + proof_url`). Distinct from
  the investor-rhetoric `Project` (which gains an alias `VcProject` for
  clarity in customer-mode contexts).
- **`Draft.mode` field** — `"vc"` or `"customer"`. The drafter sets this
  so downstream queue render / sender / cost-audit can dispatch.
- **Read-only aliases on `Draft`** — `target_email`, `target_name`,
  `lead_email`, `lead_name` all map to `investor_email` / `investor_name`
  (the v0.8.x field names). Lets customer-mode test code read fields
  with semantically appropriate names without a breaking rename.
- **`draft_email_customer(lead, proj, ...)`** — new top-level function
  exported from `vc_outreach_agent`. Default model is Haiku (volume +
  cheap), vs Sonnet for VC. Uses `skip_reflection=True` on `log_outcome`
  to avoid Haiku-on-Haiku reflection in the hot draft path.
- **8 customer-mode tests** in `tests/test_drafter_customer.py` —
  unconfigured-template / claude-subject-body / anthropic-error-fallback /
  empty-subject-fallback / lead-metadata / no-name-template /
  empty-signal-rejection / whitespace-signal-rejection. All passing.

### Changed
- Bumped `solo-founder-os` pin from `>=0.5.0` to `>=0.10.0` (customer mode
  uses `log_outcome(..., skip_reflection=True)` which only landed in 0.10).
- `Project` aliased as `VcProject` for parallel naming with
  `CustomerProject`. Both work for back-compat — existing code importing
  `Project` keeps working.
- Added `customer-outreach` and `sales` to `pyproject.toml` keywords for
  PyPI discoverability under both personas.

### Migration (existing customer-outreach-agent users)
- External users on PyPI: 0 (customer-outreach-agent was never published).
- Internal Alex use:
  ```bash
  pip uninstall customer-outreach-agent
  pip install vc-outreach-agent  # or pip install -e ~/Desktop/vc-outreach-agent
  ```
- The `customer-outreach-agent` console_script keeps resolving (now points
  at this package's `main_customer` entry).
- Existing queue files at `~/.customer-outreach-agent/queue/` keep working
  — paths are unchanged.
- The `customer-outreach-agent` GitHub repo is archived with a redirect
  README → this repo.

### Skipped from the merge plan (deferred)
- MCP server expansion to expose customer-mode tools (`draft_customer_email`,
  `list_customer_pending`). The existing VC MCP tools are unchanged. Add in
  v0.9.x or v0.10.0 once Alex actually wires customer mode into Claude
  Desktop's tool picker.
- Queue render markdown layout per-mode dispatch. Both modes currently use
  the existing VC-shaped queue render; cosmetic but visible. Address if
  reviewers complain.
- README content split per mode (current README is VC-oriented). v0.10
  task.

## [0.8.0] — 2026-05-01
See git log for prior history.

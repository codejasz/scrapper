# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable, with dev deps)
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Run scrapper (--debug is global — must come BEFORE subcommand)
source .venv/bin/activate
scrapper --debug search --service-id <ID> --city Wrocław --from "..." --to "..."                 # default: watch loop, cooldown 300s
scrapper --debug search --service-id <ID> --city Wrocław --from "..." --to "..." --once          # single sweep, exit po pierwszym przejściu
scrapper services --query <name>          # find service ID → use --service-id, not --service-name
scrapper smoke                            # connectivity check

# Tests
.venv/bin/pytest                          # unit only (no network)
.venv/bin/pytest -m smoke -s             # requires .env + network
.venv/bin/pytest tests/test_client_login.py -s   # single file
```

## Architecture

`src/scrapper/` — all source. Entry point: `cli.py:main`.

**Request flow:**
1. `LuxmedClient.login()` → JWT + XSRF cookie (10-min TTL, auto-refresh at 60s margin)
2. `catalog.py` resolves `--service-name` fuzzy → `service_id` (prompts if ambiguous)
3. `search.py` iterates day-by-day (`searchDateFrom == searchDateTo` per request), throttle 1.2–2.0s, retry-on-429 with 30s backoff; `processId` (UUID) is session-scoped and propagated across all requests
4. On match → `notify.py` Telegram alert → optional `booking.py:lock_term()` (LockTerm holds slot ~5–10 min, human confirms in UI)
5. `cli.py:_run_watch()` polls `GetUpcomingVisits` until new `eventId` appears → exit 0

**Key invariants:**
- `correlationId` in LockTerm body comes from the *last* `oneDayTerms` response, not processId
- XSRF: `XSRF-TOKEN` cookie must be duplicated as request header (double-submit pattern)
- `GetUpcomingVisits` response shape: `{"events": [...]}` — each event uses `eventId` (not `id`/`reservationId`), `doctor.name`/`doctor.lastname`, `title` (not `serviceName`)
- `--auto-book` (LockTerm) is broken — see CLI help note; default flow is alert-only

## Environment

`.env` required (see `.env.example`):
- `LUXMED_EMAIL` / `LUXMED_PASSWORD` — **wymagane** (login → JWT)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — opcjonalne; bez nich alerty są tylko logowane

Smoke tests (`pytest -m smoke`) wymagają wszystkich czterech + sieci.

Głębszy API context (endpointy, recon notes): `RECON_REPORT.md`.

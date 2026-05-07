# Handoff — Faza 2, Sesja 2: Luxmed LockTerm 400 fix

**Cel sesji:** zdiagnozować i naprawić HTTP 400 z `POST /NewPortal/Reservation/LockTerm` przez capture realnego requestu z UI Luxmed i diff z obecnym `_build_lock_term_body()`.

## State snapshot

- **Repo:** `/home/adrian/privatespace/repositories/scrapper/`
- **Branch:** `feature/scrapper-reanimacja`
- **HEAD SHA:** `af04012` (`fix(scrapper): browser-like headers + log LockTerm 4xx response body`)
- **Working tree:** modified `docs/superpowers/plans/2026-04-29-luxmed-scrapper-reanimacja.md` (stamp z sync-docs Krok 1, niezacommitowane na czas pisania handoff-u — patrz Krok 5 sync-docs).
- **Plan:** `docs/superpowers/plans/2026-04-29-luxmed-scrapper-reanimacja.md` (T1-16 DONE, T17 PARTIAL)
- **Tasklist:** `#18 [pending] Naprawić LockTerm 400 — capture realny request z UI`

## Pre-resolved decisions

Te decyzje są już podjęte — **nie reotwierać**:

- **Per-day search, NIE chunk-by-N.** Real API zwraca 1 dzień per `oneDayTerms` call. Throttle 1.2-2.0s + retry-on-429.
- **`processId` reuse w `LuxmedClient.__init__`** jako uuid4, używany dla wszystkich oneDayTerms calls.
- **`service_variant_name` wstrzykiwany z catalogu** w `cli.py:_cmd_search` przed LockTerm — real oneDayTerms response NIE zwraca tego pola na poziomie term.
- **Body LockTerm bez `processId`** per recon (`docs/superpowers/curls/lock_term.sh`). Save dostaje processId, LockTerm tylko correlationId.
- **JWT verify_signature=False** — używamy pyjwt tylko do exp claim.
- **XSRF double-submit** — cookie + header.

## Scope guard

**W scope sesji:**
- Capture realnego LockTerm requestu via Playwright/agent-browser z prawdziwego UI Luxmed.
- Diff capture vs. obecny output `_build_lock_term_body()` (`src/scrapper/client.py:221`).
- Identyfikacja brakujących/błędnych pól (body lub headers).
- Fix w `_build_lock_term_body` + update testów `tests/test_client_booking.py` + update `docs/superpowers/curls/lock_term.sh` jeśli capture pokazuje dryf.
- Re-run T17 manual validation (Step "real LockTerm with --once") aż do zielonego.
- Update planu (Task 17 PARTIAL → DONE) + tasklist (#18 → completed).

**POZA scope:**
- Refaktor architektury (search.py, client.py, cli.py) — działa, nie ruszać.
- Reanimacja flask_server / legacy main.py — skasowane w Task 14, nie wracamy.
- Nowe features (multi-service search, batch booking, etc.) — odkładamy do osobnego planu.
- Migracja na httpx/aiohttp — nie ten plan.
- Zmiana shape `.env` / Settings — stabilne.

## Pierwszy krok

1. Otwórz `docs/superpowers/curls/lock_term.sh` i `src/scrapper/client.py:221` (`_build_lock_term_body`) side-by-side — zacznij od review różnic między capture (2026-04-29) a obecnym kodem.
2. Uruchom Playwright/agent-browser sesję na `https://portalpacjenta.luxmed.pl` — login realnymi credentialami z `.env`, manualnie wybierz konsultację która ma wolne sloty (np. ortopeda Wrocław), kliknij rezerwację do momentu LockTerm, intercept request body + headers.
3. Diff capture vs. `_build_lock_term_body` output (możesz wygenerować mock output via pytest fixture lub repl).
4. Hipotezy do sprawdzenia w pierwszej kolejności:
   - Brakujące pole które dodał Angular SPA po 2026-04-29 (np. analog `partsOfDay` z Save).
   - Header anti-bot (np. nowy `x-something` w UI).
   - Inny shape `doctor` object (może `nfzId` lub coś w stylu).
   - `correlationId` mismatch — może wymaga konkretnego match z processId.
5. Po diagnozie: failing test pierwszy (TDD), potem fix.

## Verification before complete

- `pytest tests/test_client_booking.py` — green.
- Real e2e: `scrapper search --service-name "ortopeda" --city Wrocław --from "<dzisiaj+1>" --to "<dzisiaj+14>" --once --debug` — kończy się "Slot zarezerwowany: res-..." (NIE 400).
- `git status` clean (commits zacommitowane).
- Plan i tasklist zaktualizowane.

## Otwarte pytania

- Czy capture z Playwright/agent-browser nie zostawi rezerwacji "wiszącej" w koncie Adriana? — przed real LockTerm zarezerwuj timeslot ostatecznie potwierdzaj/anuluj manualnie via UI w tej samej sesji, żeby nie zaśmiecać konta.
- Czy zmieniać password Luxmed PRZED tym handoffem? — najlepiej **po** Task #18 (żeby nie unieważnić sesji w trakcie debugowania), ale to call user-a.

## Memory anchor

Snapshot stanu: `~/.claude/projects/-home-adrian-privatespace/memory/project_state_2026-05-06-luxmed-scrapper-reanimacja.md`
Pointer w `MEMORY.md` → sekcja `## Current state`.

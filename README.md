# Luxmed Scrapper

Prywatne narzędzie do automatycznej rezerwacji wizyt w Luxmedzie pod aktualne JWT-API.
Polluje dostępność, przy match-u wykonuje `LockTerm` (slot trzymany ~5-10 min) i wysyła Telegram alert.
**Confirm wykonuje człowiek** — scrapper sam nie potwierdza.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# wypełnij .env
```

`.env`:

```
LUXMED_EMAIL=...
LUXMED_PASSWORD=...
TELEGRAM_BOT_TOKEN=...   # opcjonalne
TELEGRAM_CHAT_ID=...     # opcjonalne
```

**Telegram bot:** utwórz przez @BotFather (`/newbot`), zapisz token. Wyślij `/start` do bota,
potem `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → wyciągnij `chat.id`.

## Użycie

```bash
# Lista pasujących service'ów (do --service-id):
scrapper services --query ortop

# Pollowanie + LockTerm:
scrapper search \
    --service-name "Ortopeda" \
    --city Wrocław \
    --from "2026-05-05 16:00" \
    --to "2026-05-10 19:00" \
    --doctor "Kowalski" \
    --facility "Swobodna"

# Tylko alert, bez locka:
scrapper search ... --no-lock

# Jeden sweep:
scrapper search ... --once

# Smoke (sprawdza czy API działa):
scrapper smoke
```

## Architektura

```
src/scrapper/
├── client.py        LuxmedClient — HTTP + JWT (10-min TTL, auto-refresh)
├── models.py        dataclassy: Place, Doctor, Term, SearchContext, ...
├── catalog.py       szukanie service po id/nazwie
├── search.py        SearchCriteria + per-day poll loop
├── booking.py       Save → LockTerm
├── notify.py        TelegramNotifier
├── config.py        ładowanie .env
├── logging_setup.py logger + JWT mask
└── cli.py           argparse, sub-commands
```

Per-day search: `oneDayTerms` zwraca **jeden dzień** (`searchDateFrom == searchDateTo`), iterujemy dzień-po-dniu z throttlem 1.2-2.0s między requestami + retry-on-429 z 30s backoff. Wymaga client-side `processId` (UUID) propagowanego między requestami w jednej sesji.
JWT TTL = 10 min — ponowny login przy zbliżaniu się expiry (margines 60s).
XSRF: cookie `XSRF-TOKEN` duplikowany w nagłówku (double-submit).

## Testy

```bash
.venv/bin/pytest                       # bez smoke (brak sieci)
.venv/bin/pytest -m smoke -s           # smoke (wymaga .env)
```

Smoke test: `login + serviceVariantsGroups + 1× oneDayTerms`. **Bez LockTerm.**
Cel: szybko wykryć "Luxmed znów coś zmienił".

## Bezpieczeństwo

- `.env` w `.gitignore`. Hasło tylko tam.
- JWT w logach maskowany (`eyJ...8 ostatnich znaków`).
- Po reanimacji: zmień hasło Luxmedu i wyloguj wszystkie sesje (rekomendacja z RECON_REPORT — tokeny wyciekły do transkryptów dev).

## Out of scope

- Cron / systemd unit / Docker — uruchomienie ręczne.
- Confirm — robi człowiek (klikiem albo akceptując wygaśnięcie locka).
- Cancel/rebooking — scrapper rezerwuje, nie odwołuje.
- MFA flow — current device jest `Trusted`, jeśli kiedyś przestanie — adresujemy wtedy.

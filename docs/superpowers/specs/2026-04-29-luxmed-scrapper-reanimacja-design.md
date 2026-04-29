# Design: Luxmed scrapper — reanimacja (Faza 2)

**Status:** draft, do akceptacji przez Adriana
**Data:** 2026-04-29
**Bazuje na:** `RECON_REPORT.md` z 2026-04-29 + 4 cURL-e z DevTools (login / oneDayTerms / AvailabilityLog/Save / LockTerm)
**Zakres:** dokument projektowy. **Plan implementacyjny** powstanie osobno (skill `writing-plans`) po akceptacji tego speca.

---

## Cel

Reanimacja prywatnego scrappera Luxmed pod aktualne API (Angular SPA + JWT). Po reanimacji narzędzie ma:

1. Logować się do portalu i utrzymywać sesję (z odświeżaniem JWT, który ma TTL = 10 minut).
2. Pollować dostępność wizyt z **filtrami** (service po nazwie/ID, city, zakres dat+godzin, opcjonalnie doctor/facility).
3. Po znalezieniu pasującego slotu — **automatycznie wykonać `LockTerm`** (slot trzymany przez Luxmed ~5-10 min).
4. **Powiadomić** użytkownika przez Telegram bot z linkiem do confirma.
5. **Confirm wykonuje człowiek** (klikiem w Luxmedzie albo komendą `confirm` w CLI). Scrapper sam nie potwierdza.
6. Mieć ręczny smoke test żeby szybko wyłapać kolejną zmianę API w przyszłości.

Naczelna filozofia: **prywatne narzędzie, prosto, czytelnie, bez over-engineeringu.** Średnia restrukturyzacja kodu (świeże moduły z type hints i dataclass'ami), nie pełen rewrite.

---

## Świadomie out of scope

- Flask web UI, templates, static — kasowane.
- Async/aiohttp — synchroniczny `requests` wystarczy, scrapper jest blokujący i pracuje sekwencyjnie.
- pytest, coverage, CI — nie potrzebne dla narzędzia prywatnego.
- Pełna automatyzacja confirma — bezpieczeństwo > szybkość, lockterm + Telegram daje akceptowalne okno reakcji.
- Cron / systemd unit / Docker — uruchamianie ręczne z terminala. (Można dorobić później jeśli będzie potrzeba.)
- MFA flow — JWT pokazuje `mfadevicestatus: Trusted` dla device Adriana, więc obecne logowanie nie wymaga 2FA. Jeśli kiedyś wymagać będzie — adresujemy wtedy.
- Rebooking / cancel — scrapper rezerwuje, nie odwołuje.

---

## Zmiany w kontrakcie z Luxmedem (z Fazy 1 + curle)

| Aspekt                          | Stary kod (2020)                        | Aktualny portal (2026-04)                                                                                                                               |
| ------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Login URL                       | `POST /Account/LogIn` form-data         | `POST /Account/LogIn` z **JSON body** `{"login","password"}` + `Content-Type: application/json`                                                         |
| Login response                  | HTML                                    | **JSON** `{"succeded": bool, "errorMessage": null, "token": "<JWT>", ...}`                                                                              |
| JWT TTL                         | n/a                                     | **10 minut** — wymaga refresha podczas dłuższego pollowania                                                                                             |
| Auth na kolejnych requestach    | cookie ASP.NET_SessionId                | cookie `Authorization-Token` (JWT) **+ XSRF-TOKEN** (cookie + duplikat w nagłówku)                                                                      |
| Search endpoint                 | `GET /NewPortal/terms/index`            | `GET /NewPortal/terms/**oneDayTerms**` — **per-day**, nie 14-dniowe okno                                                                                |
| Search params                   | `cityId=5` flat                         | `searchPlace.id=5&searchPlace.name=Wrocław&searchPlace.type=0` (ASP.NET model binding) + `expectedTermsNumber=1`, `pnmExecutionId`, `delocalized=false` |
| Save (preflight przed LockTerm) | `POST /availabilityLog/save`            | `POST /AvailabilityLog/Save` JSON — wciąż wymagany przed LockTerm                                                                                       |
| LockTerm                        | `POST /reservation/lockterm` form-data  | `POST /Reservation/LockTerm` JSON, **bardzo bogaty body** (z `preparationItems` które przyszły z `oneDayTerms` response)                                |
| ServiceVariantsGroups           | `GET /Dictionary/serviceVariantsGroups` | bez zmian — działa, parser z Fazy 1 OK                                                                                                                  |

Implikacje:

- **Per-day search** zmienia logikę pollowania: nie pytamy raz o 14 dni, tylko iterujemy dzień po dniu w pętli (każdy dzień osobny request). Daje to też naturalny throttling.
- **`correlationId` przychodzi z odpowiedzi** `oneDayTerms` (lub innego inicjalizującego endpointu), trzeba go potem przekazać do `Save` i `LockTerm`. Stary kod tego nie miał.
- **`preparationItems` w LockTerm** muszą być wzięte 1:1 z odpowiedzi `oneDayTerms` — klient nie wymyśla ich. To znaczy że trzeba zachować raw-term między searchem a lockiem.
- **Header `Pact: 176:997:25284:136`** — niewiadomy. Hipoteza: telemetria, prawdopodobnie nieobowiązkowy. Sprawdzimy w implementacji (najpierw bez, jeśli endpoint odrzuca → dodajemy).

---

## Architektura

Świeża struktura modułów w `src/scrapper/` (zostawiamy stary `main.py`, `flaskServer.py`, `tools.py`, `test_scrapper.py`, `templates/`, `static/` w git history — kasujemy w jednym commicie po wdrożeniu nowego kodu, żeby diff był czytelny).

```
scrapper/
├── src/scrapper/
│   ├── __init__.py
│   ├── client.py        # LuxmedClient — HTTP + JWT + XSRF + auto-refresh
│   ├── models.py        # dataclassy: Service, Place, Doctor, Term, Facility, etc.
│   ├── catalog.py       # serviceVariantsGroups → szukanie service po nazwie/ID
│   ├── search.py        # SearchCriteria + iteracja per-day + filtrowanie
│   ├── booking.py       # Save → LockTerm flow (bez Confirm)
│   ├── notify.py        # TelegramNotifier (proste send_message)
│   ├── config.py        # ładowanie .env (email, password, telegram_token, chat_id)
│   ├── logging_setup.py # konfiguracja logging (poziomy, format)
│   └── cli.py           # argparse, główna pętla, sub-commands
├── tests/
│   └── test_smoke.py    # end-to-end smoke (login + groups + 1 search), bez LockTerm
├── pyproject.toml       # PEP 621, dependencies + entry point `scrapper = scrapper.cli:main`
├── README.md            # uaktualniona instrukcja
└── .env.example         # szablon konfiguracji
```

### Moduł `client.py` — LuxmedClient

**Odpowiedzialność:** wszystkie HTTP requesty + autoryzacja + auto-refresh JWT.

**Kluczowe metody (signatures, nie implementacje):**

```python
class LuxmedClient:
    def __init__(self, email: str, password: str) -> None: ...
    def login(self) -> None: ...                              # POST /Account/LogIn JSON
    def is_authenticated(self) -> bool: ...                   # JWT obecny i ważny (z marginesem 60s)
    def ensure_authenticated(self) -> None: ...               # auto-refresh przed każdym requestem
    def get_service_groups(self) -> list[dict]: ...           # GET /Dictionary/serviceVariantsGroups
    def get_one_day_terms(
        self, *, service_id: int, place: Place, day: date,
    ) -> OneDayTermsResponse: ...                             # GET /terms/oneDayTerms
    def save_availability_log(self, search_ctx: SearchContext) -> None: ...   # POST /AvailabilityLog/Save
    def lock_term(self, term: Term) -> LockResult: ...        # POST /Reservation/LockTerm
```

**Decyzje techniczne:**

- `requests.Session()` + `Retry` z backoff (urllib3 utility) — łagodzi przejściowe 5xx i WAF blipy.
- Headery: `User-Agent: Mozilla/...`, `Accept: application/json, text/plain, */*`, `X-Requested-With: XMLHttpRequest`, `Origin: https://portalpacjenta.luxmed.pl`. Modelujemy współczesny FF.
- XSRF: po loginie wyciągamy cookie `XSRF-TOKEN`, dodajemy do `session.headers['XSRF-TOKEN']` dla **każdego** requestu po loginie (zarówno GET `oneDayTerms` w curlu ma ten header, jak i POST-y). Wartość headera musi się zgadzać z cookie (double-submit pattern).
- Auto-refresh JWT: każda publiczna metoda zaczyna się od `ensure_authenticated()`. Jeśli `exp - now < 60s`, robimy ponowny `login()`. Brak osobnego refresh-token flow (Luxmed go ma — `RefreshToken` cookie + endpoint — ale prościej re-login niż implementować refresh).
- WAF cookies (`incap_ses_*`, `visid_incap_*`) — `Session()` zarządza nimi automatycznie, nic nie robimy.
- Header `Pact: <wartość>` z curla `oneDayTerms` — pomijamy w pierwszym podejściu (hipoteza: telemetria, nieobowiązkowy). Jeśli `oneDayTerms` zwróci 400/403 — dodajemy ze stałą wartością z curla. To znana niepewność.

### Moduł `models.py` — dataclassy

Dataclassy minimum potrzebne do obsługi flow. Frozen=True gdzie to ma sens (immutability):

```python
@dataclass(frozen=True)
class Place:
    id: int
    name: str
    type: int = 0          # z curla: searchPlace.type=0

@dataclass(frozen=True)
class Doctor:
    id: int
    first_name: str
    last_name: str
    academic_title: str | None = None

@dataclass
class Term:
    """Pojedynczy dostępny slot z odpowiedzi oneDayTerms.
    Trzymamy raw_response żeby przekazać 1:1 do LockTerm bez utraty danych."""
    date_time_from: datetime
    date_time_to: datetime
    doctor: Doctor
    facility_id: int
    facility_name: str
    room_id: int
    schedule_id: int
    service_variant_id: int
    service_variant_name: str
    is_telemedicine: bool
    is_additional: bool
    raw: dict       # oryginalny dict z response, do przekazania do LockTerm
```

**Po co `raw`:** odpowiedź `oneDayTerms` zawiera pola których kod CLI nie potrzebuje rozumieć (`preparationItems`, `isPoz`, `isRehabilitation`, `isOnWhiteList`, `rehabilitationTermContext`, `eReferralId`...) ale `LockTerm` wymaga ich w body. Zamiast modelować każde pole, trzymamy raw dict i forwardujemy.

### Moduł `catalog.py` — wyszukiwanie service po nazwie

`get_service_groups()` zwraca 200 KB JSON-a z 291 examami w 3 kategoriach + zagnieżdżenie. Funkcje:

```python
def find_service_by_id(groups: list[dict], service_id: int) -> ServiceMatch | None: ...
def find_services_by_name(groups: list[dict], query: str) -> list[ServiceMatch]: ...
    # case-insensitive substring; zwraca wszystkie matche
```

Gdy CLI dostanie `--service-name "ortopeda"` i znajdzie >1 match — pokazuje listę, kończy `exit 2`. Użytkownik precyzuje albo używa `--service-id`.

### Moduł `search.py` — kryteria + pętla

```python
@dataclass
class SearchCriteria:
    service_id: int
    place: Place
    date_from: datetime          # pełen datetime (data + godzina od)
    date_to: datetime            # pełen datetime (data + godzina do)
    doctor_filter: str | None = None       # case-insensitive substring on full name
    facility_filter: str | None = None     # case-insensitive substring on facility name

def matches(term: Term, crit: SearchCriteria) -> bool:
    """Czy term pasuje do kryteriów."""

def iter_days(crit: SearchCriteria) -> Iterator[date]:
    """Yielduje kolejne daty w zakresie."""

def find_matching_term(client: LuxmedClient, crit: SearchCriteria) -> Term | None:
    """Jeden 'sweep' przez wszystkie dni w zakresie. Zwraca pierwszy match lub None."""

def poll_loop(
    client: LuxmedClient, crit: SearchCriteria, *,
    sleep_min: int = 30, sleep_max: int = 90,
    max_iterations: int | None = None,
) -> Term:
    """Pętla pollowania. Blokująca. Zwraca pasujący term albo wyrzuca KeyboardInterrupt."""
```

**Decyzja dot. interwału:** stary kod używał 15-45s. Z curli widać że WAF (Imperva) jest aktywny — bezpieczniej 30-90s, mniej ryzyko że nas zbanują.

### Moduł `booking.py` — Save + LockTerm

```python
def lock(client: LuxmedClient, term: Term, search_ctx: SearchContext) -> LockResult:
    """1. Save — telemetria/log dla Luxmedu (wymagana przed LockTerm).
       2. LockTerm — rezerwacja tymczasowa (~5-10 min)."""
```

`SearchContext` to mały dataclass z `processId` (UUID generowany na początku sesji search), `correlationId` (przychodzi z oneDayTerms response), `searchParameters` (dla Save call).

### Moduł `notify.py` — Telegram

```python
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None: ...
    def send(self, text: str) -> None:
        """POST do https://api.telegram.org/bot<token>/sendMessage.
        Markdown lub HTML formatting. Failure loguje warning, nie wyrzuca — powiadomienie nie ma blokować flow.
        """
```

Treść powiadomienia: imię lekarza, godzina, klinika, link do strony rezerwacji w Luxmedzie. Konkretny URL gdzie user dokończy confirm — do potwierdzenia podczas implementacji (kandydaci: `/PatientPortal/NewPortal/Page/Reservation/Results`, `/PatientPortal/NewPortal/Page/MyVisits`). Domyślnie linkujemy do strony głównej portalu jeśli niejasne — user trafi i kliknie sam.

### Moduł `config.py` — `.env` z `python-dotenv`

```
LUXMED_EMAIL=...
LUXMED_PASSWORD=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

`config.py` (stary, w roocie repo, surowy email/password) — kasujemy. `.env` w gitignore. `.env.example` w repo z placeholderami.

### Moduł `cli.py` — sub-commands

```
scrapper search \
    [--service-id 4436 | --service-name "Ortopeda"] \
    --city "Wrocław" \
    --from "2026-05-05 16:00" \
    --to   "2026-05-10 19:00" \
    [--doctor "KOWALSKI"] \
    [--facility "Swobodna"] \
    [--once]                    # jeden sweep, bez pollowania
    [--no-lock]                 # tylko alert, bez LockTerm
    [--max-iterations N]

scrapper services [--query "ortop"]    # listuje matching services z grup, pomocne do --service-id

scrapper smoke                         # uruchamia smoke test (login + groups + 1 search bez locka)
```

**Logging:** `logging_setup.py` konfiguruje root logger:

- INFO domyślnie do stdout (czytelny "Szukam... znaleziono X dni... brak match... śpię 60s...")
- DEBUG do `~/.luxmed-scrapper/scrapper.log` (jeśli `--debug`)
- Brak `print()` w kodzie produkcyjnym.

### Moduł `tests/test_smoke.py`

Jeden test, ręcznie odpalany przez `scrapper smoke` lub `pytest tests/test_smoke.py`:

1. Login z `.env` credentials
2. Pobierz `serviceVariantsGroups`, sprawdź że ma >0 entries
3. Wybierz pierwszy service z pierwszej kategorii, zrób `oneDayTerms` na dziś
4. Sprawdź że status 200 i response to JSON

**Bez LockTerm.** Cel: szybko wykryć "Luxmed znów coś zmienił". Brak mocków — to faktyczny end-to-end.

---

## Flow użytkownika (happy path)

1. Setup (jednorazowo): `.env` z 4 zmiennymi, Telegram bot utworzony przez @BotFather, `chat_id` znaleziony przez wysłanie `/start` do bota i sprawdzenie `getUpdates`.
2. Adrian uruchamia: `scrapper search --service-name "Ortopeda" --city Wrocław --from "2026-05-05 16:00" --to "2026-05-10 19:00"`
3. Scrapper loguje: "Znaleziono service: 4436 — Konsultacja ortopedyczna"
4. Pętla: dla każdego dnia w zakresie → `oneDayTerms` → filtruj `matches()` → jeśli match, break.
5. Brak match → log "brak slotów, śpię 60s" → `time.sleep(60)` → goto 4.
6. Match znaleziony → `Save` → `LockTerm` → log "Slot zarezerwowany tymczasowo: dr X, 8.05 17:00, klinika Y"
7. Telegram message z linkiem do MyVisits + szczegóły slotu.
8. Scrapper kończy `exit 0`. Lock wygaśnie sam za 5-10 min jeśli Adrian nic nie zrobi. Adrian klika confirm w przeglądarce (lub akceptuje wygaśnięcie).

## Error handling

- **Login fails (succeded=False):** wyrzuca `AuthError`, CLI loguje czytelny błąd i `exit 1`.
- **JWT expires podczas pollowania:** auto-refresh w `ensure_authenticated()`. Jeśli refresh fails — `AuthError`, CLI exit.
- **HTTP 5xx z Luxmedu:** retry 3 razy z backoff. Po 3 nieudanych — log warn, kontynuuj polling (Luxmed bywa kapryśny, nie chcemy że jeden 500 zatrzyma scrapper na noc).
- **WAF block (Imperva 429/403 z Incapsula HTML):** log error, sleep 5 minut, kontynuuj. Jeśli powtórzy się 3 razy — exit z błędem.
- **Telegram fails:** log warn, kontynuuj. Powiadomienie jest "best effort" — slot już zlockowany, Adrian może sprawdzić MyVisits.
- **LockTerm fails:** log error, scrapper kończy z `exit 1` (nie próbujemy znów — slot prawdopodobnie ktoś inny chwycił w międzyczasie).
- **`SyntaxWarning` na `\s` w starym kodzie** — nie problem, kod kasujemy.

## Bezpieczeństwo

- `.env` w `.gitignore`. Przy commitcie ustawić git pre-commit hook? **Nie** — overhead, polegamy na `.gitignore`.
- Hasła nie do logów (logging mask).
- JWT do logów tylko maskowany (`eyJ...` + ostatnie 8 znaków).
- Po Fazie 2: Adrian zmienia hasło Luxmedu i wylogowuje wszystkie sesje (rekomendacja z RECON_REPORT — w transkrypcie były tokeny).

---

## Kryteria sukcesu (acceptance criteria)

Faza 2 jest skończona gdy:

- [ ] `scrapper search` z prawidłowymi flagami znajdzie wizytę na dziś/jutro i zlockuje ją (testowane na służbie z którą jest dużo wolnych terminów, np. fizjoterapeuta).
- [ ] Telegram bot dostaje wiadomość z linkiem.
- [ ] `scrapper smoke` przechodzi.
- [ ] `scrapper services --query "ortop"` zwraca matching services.
- [ ] Stary `main.py`, `flaskServer.py`, `tools.py`, `test_scrapper.py`, `templates/`, `static/` skasowane jednym commitem.
- [ ] `.env.example` w repo, `.env` ignorowany.
- [ ] README zaktualizowany pod nowy CLI (z setupem Telegram bot).
- [ ] Brak `print()` w kodzie produkcyjnym (poza `cli.py` jeśli wygodnie).
- [ ] Adrian zmienił hasło i wylogował sesje w Luxmedzie po zakończeniu prac.

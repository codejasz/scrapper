# Luxmed Scrapper Reanimacja — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reanimować prywatny scrapper Luxmed pod aktualne JWT-API: per-day search z filtrami, automatyczny LockTerm, powiadomienie na Telegram, ręczny smoke test.

**Architecture:** Świeży pakiet `src/scrapper/` z wąskimi modułami (client, models, catalog, search, booking, notify, config, cli). `requests.Session()` z auto-refreshem JWT (10-min TTL przez ponowny login). Per-day pollowanie z double-submit XSRF. Stary kod (`main.py`, `flaskServer.py`, `tools.py`, `templates/`, `static/`) skasowany w jednym commicie po wdrożeniu nowego.

**Tech Stack:** Python 3.13, `requests`, `python-dotenv`, `python-dateutil`, `pyjwt` (do dekodowania `exp`), `pytest` (smoke), `pyproject.toml` (PEP 621), entry point `scrapper = scrapper.cli:main`.

**Spec:** `docs/superpowers/specs/2026-04-29-luxmed-scrapper-reanimacja-design.md`

**Plik struktura (target):**

```
scrapper/
├── src/scrapper/
│   ├── __init__.py
│   ├── client.py           # LuxmedClient (HTTP + JWT + XSRF + auto-refresh)
│   ├── models.py           # dataclassy: Place, Doctor, Term, SearchContext, LockResult, OneDayTermsResponse
│   ├── catalog.py          # find_service_by_id / find_services_by_name
│   ├── search.py           # SearchCriteria, matches(), iter_days(), find_matching_term(), poll_loop()
│   ├── booking.py          # lock(client, term, ctx) → Save → LockTerm
│   ├── notify.py           # TelegramNotifier
│   ├── config.py           # ładowanie .env (Settings dataclass)
│   ├── logging_setup.py    # konfiguracja logging + JWT mask
│   └── cli.py              # argparse, sub-commands: search / services / smoke
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_catalog.py
│   ├── test_search_filtering.py
│   ├── test_logging_mask.py
│   └── test_smoke.py       # end-to-end (login + groups + 1 search)
├── docs/superpowers/
│   ├── specs/2026-04-29-...md
│   ├── plans/2026-04-29-...md   ← ten plik
│   └── curls/                   ← artefakty referencyjne (Task 1)
├── pyproject.toml
├── README.md
├── .env.example
└── .gitignore                   ← uzupełniony
```

**Konwencje commitów:** `feat(scrapper): ...`, `fix(scrapper): ...`, `chore(scrapper): ...`, `docs(scrapper): ...`, `test(scrapper): ...`, `refactor(scrapper): ...`. Wszystkie commity z scope `scrapper`.

---

## Task 0: Pre-flight — zażądaj cURL-i i podmień plaintext password

**Files:**

- Create: `docs/superpowers/curls/README.md`
- Create: `docs/superpowers/curls/.gitkeep`
- Modify: `config.py` (root) — usunąć plaintext password (zostawić plik do skasowania w Task 14)
- Modify: `.gitignore` — dodać artefakty

**Cel:** Spec deklaruje że bazujemy na 4 cURL-ach z DevTools (`login`, `oneDayTerms`, `AvailabilityLog/Save`, `LockTerm`), ale w repo ich nie ma. Implementator MUSI je zobaczyć przed pisaniem `client.py`, bo headery i payloady są nietrywialne (XSRF double-submit, `searchPlace.id/.name/.type`, `preparationItems`, `processId`/`correlationId`).

- [ ] **Step 1: Utwórz katalog na cURL-e i README z instrukcją**

```bash
mkdir -p docs/superpowers/curls
touch docs/superpowers/curls/.gitkeep
```

Utwórz `docs/superpowers/curls/README.md`:

```markdown
# cURL artefakty z DevTools

Surowe `Copy as cURL` z Firefox/Chrome DevTools dla 4 endpointów Luxmed.
Te pliki są **referencją dla implementacji** `src/scrapper/client.py` —
zawierają kompletne headery, cookies, body.

**Wymagane pliki (do dodania ręcznie przez Adriana, nie commitować jeśli zawierają hasło/JWT):**

- `login.sh` — POST /Account/LogIn (JSON body)
- `one_day_terms.sh` — GET /NewPortal/terms/oneDayTerms?...
- `availability_save.sh` — POST /NewPortal/AvailabilityLog/Save
- `lock_term.sh` — POST /NewPortal/Reservation/LockTerm

**Bezpieczeństwo:** te pliki zawierają JWT, hasło, cookies sesyjne.
Są w `.gitignore` (patrz niżej). Po Fazie 2 Adrian zmieni hasło Luxmedu i
wylogowuje wszystkie sesje — wtedy artefakty stracą wartość atakującego.
```

- [ ] **Step 2: Dodaj artefakty do `.gitignore`**

Edytuj `.gitignore`. Obecna treść (`config.py`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `responses/`) — dodaj na końcu:

```
# cURL artefakty (zawierają sesyjne JWT/hasła — nie commitować)
docs/superpowers/curls/*.sh
docs/superpowers/curls/*.txt
!docs/superpowers/curls/README.md
!docs/superpowers/curls/.gitkeep

# Nowe artefakty implementacji
.env
__pycache__/
.pytest_cache/
*.egg-info/
build/
dist/
~/.luxmed-scrapper/
scrapper.log
```

- [ ] **Step 3: Wyzeruj plaintext password w `config.py` (do czasu skasowania w Task 14)**

Plik `config.py` w roocie zawiera plaintext hasło Adriana. Nawet jeśli skasujemy go w Task 14, do tego czasu nie zostawiamy go w worktree. Zastąp całą zawartość:

```python
# DEPRECATED — to be deleted in Task 14. Use src/scrapper/config.py + .env instead.
email = ""
password = ""
```

- [ ] **Step 4: STOP — poproś użytkownika**

Wypisz w odpowiedzi do użytkownika:

> Przed dalszą implementacją potrzebuję 4 cURL-i z DevTools w `docs/superpowers/curls/`:
> `login.sh`, `one_day_terms.sh`, `availability_save.sh`, `lock_term.sh`.
> Otwórz portalpacjenta.luxmed.pl, zaloguj się, w DevTools → Network kliknij prawym → Copy → Copy as cURL dla każdego z 4 requestów (login + 1 search dnia + Save + LockTerm na dowolnym wolnym slocie). Wklej do plików.
> Pliki są w `.gitignore` — nie wycieką do publicznego repo.
> Po wklejeniu — kontynuuj plan od Task 1.

Czekaj na potwierdzenie przed Task 1.

- [ ] **Step 5: Commit (bez cURL-i, tylko strukturę)**

```bash
git add .gitignore config.py docs/superpowers/curls/README.md docs/superpowers/curls/.gitkeep docs/superpowers/plans/
git commit -m "chore(scrapper): redact plaintext credentials, prep curl artefakty dir"
```

---

## Task 1: pyproject.toml + struktura pakietu

**Files:**

- Create: `pyproject.toml`
- Create: `src/scrapper/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Utwórz `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "luxmed-scrapper"
version = "0.2.0"
description = "Prywatny scrapper rezerwacji wizyt Luxmed (JWT-era)"
readme = "README.md"
requires-python = ">=3.11"
license = {file = "LICENSE"}
authors = [{name = "Adrian Kodjasz", email = "adrian.kodjasz@gmail.com"}]
dependencies = [
    "requests>=2.31",
    "python-dotenv>=1.0",
    "python-dateutil>=2.8",
    "pyjwt>=2.8",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
scrapper = "scrapper.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Utwórz `src/scrapper/__init__.py`**

```python
"""Luxmed scrapper — prywatne narzędzie do rezerwacji wizyt."""

__version__ = "0.2.0"
```

- [ ] **Step 3: Utwórz `tests/__init__.py` (puste)**

```python

```

- [ ] **Step 4: Utwórz `tests/conftest.py`**

```python
"""Pytest fixtures wspólne dla całego testowego zestawu."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def env_loaded(repo_root: Path) -> None:
    """Smoke testom potrzebny .env. Pomija test jeśli brak."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        pytest.skip(".env not present — skip end-to-end smoke")
    from dotenv import load_dotenv
    load_dotenv(env_path)
    if not os.environ.get("LUXMED_EMAIL"):
        pytest.skip("LUXMED_EMAIL nie ustawiony")
```

- [ ] **Step 5: Zainstaluj pakiet w editable mode i sprawdź że importuje**

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -c "import scrapper; print(scrapper.__version__)"
```

Expected: `0.2.0`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/scrapper/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore(scrapper): scaffold pyproject.toml + package layout"
```

---

## Task 2: config.py — Settings z .env

**Files:**

- Create: `src/scrapper/config.py`
- Create: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Utwórz failing test `tests/test_config.py`**

```python
import pytest

from scrapper.config import Settings, load_settings


def test_load_settings_reads_all_four_env_vars(monkeypatch):
    monkeypatch.setenv("LUXMED_EMAIL", "a@b.pl")
    monkeypatch.setenv("LUXMED_PASSWORD", "secret123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    settings = load_settings(load_dotenv_file=False)

    assert isinstance(settings, Settings)
    assert settings.luxmed_email == "a@b.pl"
    assert settings.luxmed_password == "secret123"
    assert settings.telegram_bot_token == "123:abc"
    assert settings.telegram_chat_id == "42"


def test_load_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("LUXMED_EMAIL", raising=False)
    monkeypatch.delenv("LUXMED_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="LUXMED_EMAIL"):
        load_settings(load_dotenv_file=False)


def test_load_settings_telegram_optional(monkeypatch):
    monkeypatch.setenv("LUXMED_EMAIL", "a@b.pl")
    monkeypatch.setenv("LUXMED_PASSWORD", "x")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    settings = load_settings(load_dotenv_file=False)

    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'scrapper.config'`

- [ ] **Step 3: Implement `src/scrapper/config.py`**

```python
"""Konfiguracja z .env. Telegram opcjonalny — bez niego notify wyłączony."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    luxmed_email: str
    luxmed_password: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_settings(*, load_dotenv_file: bool = True, env_path: Path | None = None) -> Settings:
    if load_dotenv_file:
        load_dotenv(env_path)

    email = os.environ.get("LUXMED_EMAIL")
    password = os.environ.get("LUXMED_PASSWORD")
    if not email:
        raise RuntimeError("LUXMED_EMAIL nie ustawiony (sprawdź .env)")
    if not password:
        raise RuntimeError("LUXMED_PASSWORD nie ustawiony (sprawdź .env)")

    return Settings(
        luxmed_email=email,
        luxmed_password=password,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
    )
```

- [ ] **Step 4: Utwórz `.env.example`**

```
LUXMED_EMAIL=
LUXMED_PASSWORD=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

- [ ] **Step 5: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/scrapper/config.py .env.example tests/test_config.py
git commit -m "feat(scrapper): config loader z .env i opcjonalnym Telegramem"
```

---

## Task 3: logging_setup.py — root logger + JWT mask

**Files:**

- Create: `src/scrapper/logging_setup.py`
- Test: `tests/test_logging_mask.py`

- [ ] **Step 1: Utwórz failing test `tests/test_logging_mask.py`**

```python
import logging

from scrapper.logging_setup import JwtMaskingFilter, mask_jwt, setup_logging


def test_mask_jwt_keeps_prefix_and_last_8_chars():
    token = "eyJ" + "A" * 100 + "deadbeef"
    masked = mask_jwt(token)
    assert masked.startswith("eyJ")
    assert masked.endswith("deadbeef")
    assert "..." in masked
    assert len(masked) < len(token)


def test_mask_jwt_short_token_fully_masked():
    assert mask_jwt("short") == "***"


def test_mask_jwt_none_returns_none():
    assert mask_jwt(None) is None


def test_filter_redacts_jwt_in_message(caplog):
    setup_logging(verbose=False)
    logger = logging.getLogger("scrapper.test")
    logger.addFilter(JwtMaskingFilter())

    fake_jwt = "eyJhbGciOiJIUzI1NiJ9." + "x" * 100 + ".signature"
    with caplog.at_level(logging.INFO, logger="scrapper.test"):
        logger.info("Got token=%s done", fake_jwt)

    assert any("eyJhbGci" in r.getMessage() for r in caplog.records)
    assert not any(("x" * 100) in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_logging_mask.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/scrapper/logging_setup.py`**

```python
"""Konfiguracja logging + filter maskujący JWT w wiadomościach."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]+){1,2}")


def mask_jwt(token: str | None) -> str | None:
    if token is None:
        return None
    if len(token) < 16:
        return "***"
    return f"{token[:8]}...{token[-8:]}"


class JwtMaskingFilter(logging.Filter):
    """Zamienia każdy JWT-looking ciąg w `record.msg`/argumentach na maskowany."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        masked = JWT_PATTERN.sub(lambda m: mask_jwt(m.group(0)) or "***", message)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(*, verbose: bool = False, log_file: Path | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    console.addFilter(JwtMaskingFilter())
    root.addHandler(console)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fileh = logging.FileHandler(log_file, encoding="utf-8")
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(fmt)
        fileh.addFilter(JwtMaskingFilter())
        root.addHandler(fileh)
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_logging_mask.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/logging_setup.py tests/test_logging_mask.py
git commit -m "feat(scrapper): logging setup z filtrem maskującym JWT"
```

---

## Task 4: models.py — dataclassy

**Files:**

- Create: `src/scrapper/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Utwórz failing test `tests/test_models.py`**

```python
from datetime import datetime

import pytest

from scrapper.models import (
    Doctor,
    LockResult,
    OneDayTermsResponse,
    Place,
    SearchContext,
    Term,
)


def test_place_is_frozen():
    p = Place(id=5, name="Wrocław")
    assert p.type == 0
    with pytest.raises(Exception):
        p.id = 99  # frozen


def test_doctor_full_name_with_title():
    d = Doctor(id=1, first_name="Jan", last_name="Kowalski", academic_title="dr")
    assert d.full_name() == "dr Jan Kowalski"


def test_doctor_full_name_without_title():
    d = Doctor(id=1, first_name="Jan", last_name="Kowalski", academic_title=None)
    assert d.full_name() == "Jan Kowalski"


def test_term_keeps_raw_for_lockterm_payload():
    raw = {"preparationItems": [{"id": 1}], "isPoz": False, "extra": "anything"}
    doctor = Doctor(id=10, first_name="A", last_name="B")
    term = Term(
        date_time_from=datetime(2026, 5, 8, 17, 0),
        date_time_to=datetime(2026, 5, 8, 17, 30),
        doctor=doctor,
        facility_id=20,
        facility_name="Klinika",
        room_id=30,
        schedule_id=40,
        service_variant_id=4436,
        service_variant_name="Ortopeda",
        is_telemedicine=False,
        is_additional=False,
        raw=raw,
    )
    assert term.raw["preparationItems"] == [{"id": 1}]


def test_search_context_holds_correlation_and_process_ids():
    ctx = SearchContext(
        process_id="abc-123",
        correlation_id="corr-456",
        search_parameters={"serviceVariantId": 4436},
    )
    assert ctx.process_id == "abc-123"
    assert ctx.correlation_id == "corr-456"


def test_one_day_terms_response_carries_correlation_id():
    resp = OneDayTermsResponse(
        terms=[],
        correlation_id="xyz",
        raw={"correlationId": "xyz", "termsForService": {"termsForDays": []}},
    )
    assert resp.correlation_id == "xyz"
    assert resp.terms == []


def test_lock_result_success_or_failure():
    ok = LockResult(success=True, temporary_reservation_id="res-1", error=None, raw={})
    fail = LockResult(success=False, temporary_reservation_id=None, error="slot zajęty", raw={})
    assert ok.success is True
    assert fail.error == "slot zajęty"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_models.py -v
```

Expected: FAIL `ImportError`

- [ ] **Step 3: Implement `src/scrapper/models.py`**

```python
"""Dataclassy domeny — tyle pól ile potrzebne dla flow search → save → lock."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Place:
    id: int
    name: str
    type: int = 0


@dataclass(frozen=True)
class Doctor:
    id: int
    first_name: str
    last_name: str
    academic_title: str | None = None

    def full_name(self) -> str:
        if self.academic_title:
            return f"{self.academic_title} {self.first_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


@dataclass
class Term:
    """Pojedynczy slot z `oneDayTerms`. `raw` trzymamy żeby przekazać 1:1 do LockTerm."""

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
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchContext:
    """Stan sesji wyszukiwania potrzebny do Save/LockTerm."""

    process_id: str
    correlation_id: str | None
    search_parameters: dict[str, Any]


@dataclass
class OneDayTermsResponse:
    terms: list[Term]
    correlation_id: str | None
    raw: dict[str, Any]


@dataclass
class LockResult:
    success: bool
    temporary_reservation_id: str | None
    error: str | None
    raw: dict[str, Any]
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_models.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/models.py tests/test_models.py
git commit -m "feat(scrapper): dataclassy domeny (Place, Doctor, Term, SearchContext, ...)"
```

---

## Task 5: catalog.py — wyszukiwanie service po nazwie/ID

**Files:**

- Create: `src/scrapper/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Utwórz failing test `tests/test_catalog.py`**

```python
import pytest

from scrapper.catalog import (
    ServiceMatch,
    find_service_by_id,
    find_services_by_name,
)


@pytest.fixture
def groups_fixture() -> list[dict]:
    """Skrócony kształt `serviceVariantsGroups` z prawdziwego endpointu."""
    return [
        {
            "id": 1,
            "name": "Konsultacje",
            "children": [
                {
                    "id": 100,
                    "name": "Ortopedia",
                    "children": [
                        {"id": 4436, "name": "Konsultacja ortopedyczna", "children": []},
                        {"id": 4437, "name": "Ortopeda dziecięcy", "children": []},
                    ],
                },
                {
                    "id": 101,
                    "name": "Inne",
                    "children": [
                        {"id": 9999, "name": "Coś innego", "children": []},
                    ],
                },
            ],
        }
    ]


def test_find_service_by_id_returns_match(groups_fixture):
    match = find_service_by_id(groups_fixture, 4436)
    assert isinstance(match, ServiceMatch)
    assert match.service_id == 4436
    assert match.name == "Konsultacja ortopedyczna"
    assert match.path == ["Konsultacje", "Ortopedia", "Konsultacja ortopedyczna"]


def test_find_service_by_id_missing_returns_none(groups_fixture):
    assert find_service_by_id(groups_fixture, 1) is None


def test_find_services_by_name_substring_case_insensitive(groups_fixture):
    matches = find_services_by_name(groups_fixture, "ortop")
    ids = sorted(m.service_id for m in matches)
    assert ids == [4436, 4437]


def test_find_services_by_name_no_match(groups_fixture):
    assert find_services_by_name(groups_fixture, "kardio") == []


def test_find_services_by_name_empty_query_returns_empty(groups_fixture):
    assert find_services_by_name(groups_fixture, "") == []
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_catalog.py -v
```

Expected: FAIL `ImportError`

- [ ] **Step 3: Implement `src/scrapper/catalog.py`**

```python
"""Płaska iteracja po drzewie serviceVariantsGroups."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceMatch:
    service_id: int
    name: str
    path: list[str]


def _walk(groups: list[dict], path: list[str]) -> Iterator[ServiceMatch]:
    for node in groups:
        node_id = node.get("id")
        node_name = node.get("name", "")
        children = node.get("children") or []
        new_path = [*path, node_name]
        if not children:
            if node_id is not None:
                yield ServiceMatch(service_id=node_id, name=node_name, path=new_path)
        else:
            yield from _walk(children, new_path)


def find_service_by_id(groups: list[dict], service_id: int) -> ServiceMatch | None:
    for match in _walk(groups, []):
        if match.service_id == service_id:
            return match
    return None


def find_services_by_name(groups: list[dict], query: str) -> list[ServiceMatch]:
    if not query:
        return []
    needle = query.casefold()
    return [m for m in _walk(groups, []) if needle in m.name.casefold()]
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_catalog.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/catalog.py tests/test_catalog.py
git commit -m "feat(scrapper): catalog z lookupem service po id/nazwie"
```

---

## Task 6: client.py — szkielet LuxmedClient + login

**Files:**

- Create: `src/scrapper/client.py`
- Test: `tests/test_client_login.py`

**Cel tego tasku:** tylko login flow (POST `/Account/LogIn` JSON, parsowanie `{succeded, token, ...}`, ustawienie `Authorization-Token` cookie + JWT w headerze). XSRF, oneDayTerms, Save, LockTerm — kolejne taski.

**Ważne:** zanim zaczniesz, otwórz `docs/superpowers/curls/login.sh` — patrz dokładnie jakie headery wysyła przeglądarka. Ten test mockuje response, ale headery requestu muszą być jak w cURL-u.

- [ ] **Step 1: Utwórz failing test `tests/test_client_login.py`**

```python
import json
import time

import pytest
import requests
from requests.adapters import HTTPAdapter

from scrapper.client import AuthError, LuxmedClient


class _MockAdapter(HTTPAdapter):
    """Adapter który zwraca przygotowane response'y zamiast iść w sieć."""

    def __init__(self, responses: list[tuple[int, dict, dict]]):
        super().__init__()
        self._responses = list(responses)
        self.calls: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.calls.append(request)
        status, headers, body = self._responses.pop(0)
        resp = requests.Response()
        resp.status_code = status
        resp.headers.update(headers)
        resp._content = json.dumps(body).encode("utf-8")
        resp.url = request.url
        resp.request = request
        return resp


def _make_jwt(exp_seconds_from_now: int) -> str:
    import jwt
    payload = {"exp": int(time.time()) + exp_seconds_from_now, "sub": "user"}
    return jwt.encode(payload, "secret", algorithm="HS256")


def test_login_success_stores_token():
    jwt_token = _make_jwt(600)
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json"}, {
            "succeded": True,
            "errorMessage": None,
            "token": jwt_token,
        }),
    ])
    client = LuxmedClient("a@b.pl", "secret")
    client.session.mount("https://", adapter)

    client.login()

    assert client.is_authenticated()
    sent = adapter.calls[0]
    assert sent.method == "POST"
    assert sent.url.endswith("/Account/LogIn")
    body = json.loads(sent.body)
    assert body == {"login": "a@b.pl", "password": "secret"}
    assert sent.headers["Content-Type"].startswith("application/json")


def test_login_failure_raises_auth_error():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json"}, {
            "succeded": False,
            "errorMessage": "Nieprawidłowy login lub hasło",
            "token": None,
        }),
    ])
    client = LuxmedClient("a@b.pl", "wrong")
    client.session.mount("https://", adapter)

    with pytest.raises(AuthError, match="Nieprawid"):
        client.login()


def test_is_authenticated_false_when_no_token():
    client = LuxmedClient("a@b.pl", "x")
    assert client.is_authenticated() is False


def test_is_authenticated_false_when_token_near_expiry():
    client = LuxmedClient("a@b.pl", "x")
    client._token = _make_jwt(30)  # under 60s margin
    assert client.is_authenticated() is False


def test_ensure_authenticated_relogins_when_needed():
    jwt1 = _make_jwt(600)
    jwt2 = _make_jwt(600)
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json"},
         {"succeded": True, "errorMessage": None, "token": jwt1}),
        (200, {"Content-Type": "application/json"},
         {"succeded": True, "errorMessage": None, "token": jwt2}),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)

    client.ensure_authenticated()  # logs in
    assert client.is_authenticated()

    client._token = _make_jwt(30)  # force expiry
    client.ensure_authenticated()  # should relogin

    assert len(adapter.calls) == 2
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_client_login.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'scrapper.client'`

- [ ] **Step 3: Implement `src/scrapper/client.py` (login-only szkielet)**

```python
"""LuxmedClient — HTTP + JWT. Inne endpointy dochodzą w kolejnych taskach."""

from __future__ import annotations

import logging
import time
from typing import Any

import jwt as jwt_lib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://portalpacjenta.luxmed.pl/PatientPortal"
LOGIN_URL = f"{BASE_URL}/Account/LogIn"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    "Origin": "https://portalpacjenta.luxmed.pl",
    "Referer": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal",
    "X-Requested-With": "XMLHttpRequest",
}

JWT_EXPIRY_MARGIN_SECONDS = 60


class AuthError(RuntimeError):
    pass


class LuxmedClient:
    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self._token: str | None = None

        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def login(self) -> None:
        logger.info("Logowanie do Luxmed (%s)", self.email)
        resp = self.session.post(
            LOGIN_URL,
            json={"login": self.email, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("succeded"):
            raise AuthError(data.get("errorMessage") or "Login failed (succeded=False)")
        token = data.get("token")
        if not token:
            raise AuthError("Login response bez pola token")
        self._token = token
        self.session.headers["Authorization-Token"] = token
        logger.info("Zalogowano. Token przydzielony.")

    def is_authenticated(self) -> bool:
        if not self._token:
            return False
        try:
            payload: dict[str, Any] = jwt_lib.decode(
                self._token, options={"verify_signature": False, "verify_exp": False}
            )
        except jwt_lib.PyJWTError:
            return False
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return False
        return exp - time.time() > JWT_EXPIRY_MARGIN_SECONDS

    def ensure_authenticated(self) -> None:
        if not self.is_authenticated():
            self.login()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_client_login.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/client.py tests/test_client_login.py
git commit -m "feat(scrapper): LuxmedClient z login + JWT auto-refresh"
```

---

## Task 7: client.py — XSRF + serviceVariantsGroups

**Files:**

- Modify: `src/scrapper/client.py`
- Test: `tests/test_client_groups.py`

- [ ] **Step 1: Utwórz failing test `tests/test_client_groups.py`**

```python
import json
import time

import jwt as jwt_lib

from scrapper.client import LuxmedClient

from .test_client_login import _MockAdapter


def _jwt(exp: int = 600) -> str:
    return jwt_lib.encode({"exp": int(time.time()) + exp}, "s", algorithm="HS256")


def test_get_service_groups_returns_parsed_list_and_sets_xsrf_header():
    adapter = _MockAdapter([
        (200,
         {"Content-Type": "application/json",
          "Set-Cookie": "XSRF-TOKEN=xsrfvalue123; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"},
         [{"id": 1, "name": "Konsultacje", "children": []}]),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)

    client.login()
    groups = client.get_service_groups()

    assert isinstance(groups, list)
    assert groups[0]["name"] == "Konsultacje"

    groups_request = adapter.calls[1]
    assert groups_request.headers.get("XSRF-TOKEN") == "xsrfvalue123"
    assert groups_request.headers.get("Authorization-Token") is not None
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_client_groups.py -v
```

Expected: FAIL `AttributeError: 'LuxmedClient' object has no attribute 'get_service_groups'`

- [ ] **Step 3: Rozszerz `src/scrapper/client.py`** — dodaj XSRF i `get_service_groups`

Dodaj na górze stałą:

```python
GROUPS_URL = f"{BASE_URL}/NewPortal/Dictionary/serviceVariantsGroups"
```

W `login()` po przypisaniu tokenu (przed log "Zalogowano") dodaj propagację XSRF:

```python
        self._token = token
        self.session.headers["Authorization-Token"] = token
        self._propagate_xsrf()
        logger.info("Zalogowano. Token przydzielony.")
```

Dodaj metody w klasie `LuxmedClient`:

```python
    def _propagate_xsrf(self) -> None:
        """Double-submit XSRF: cookie XSRF-TOKEN duplikujemy w header'ze."""
        xsrf = self.session.cookies.get("XSRF-TOKEN")
        if xsrf:
            self.session.headers["XSRF-TOKEN"] = xsrf

    def get_service_groups(self) -> list[dict]:
        self.ensure_authenticated()
        self._propagate_xsrf()
        resp = self.session.get(GROUPS_URL)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_client_groups.py -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/client.py tests/test_client_groups.py
git commit -m "feat(scrapper): XSRF double-submit + getServiceGroups"
```

---

## Task 8: client.py — oneDayTerms (per-day search)

**Files:**

- Modify: `src/scrapper/client.py`
- Test: `tests/test_client_oneday.py`

**Referencja:** `docs/superpowers/curls/one_day_terms.sh` — query string ma flat-binding `searchPlace.id=5&searchPlace.name=Wrocław&searchPlace.type=0&serviceVariantId=4436&languageId=10&searchDateFrom=2026-05-08&searchDatePreset=14&expectedTermsNumber=1&pnmExecutionId=...&delocalized=false`. **Skopiuj parametry 1:1**, oprócz dynamicznych (`searchDateFrom`, `serviceVariantId`, `searchPlace.*`).

- [ ] **Step 1: Utwórz failing test `tests/test_client_oneday.py`**

```python
import json
import time
from datetime import date

import jwt as jwt_lib

from scrapper.client import LuxmedClient
from scrapper.models import Place

from .test_client_login import _MockAdapter


def _jwt() -> str:
    return jwt_lib.encode({"exp": int(time.time()) + 600}, "s", algorithm="HS256")


_SAMPLE_TERMS_RESPONSE = {
    "correlationId": "corr-abc",
    "termsForService": {
        "termsForDays": [
            {
                "day": "2026-05-08",
                "terms": [
                    {
                        "dateTimeFrom": "2026-05-08T17:00:00",
                        "dateTimeTo": "2026-05-08T17:30:00",
                        "doctor": {
                            "id": 11, "firstName": "Jan", "lastName": "Kowalski",
                            "academicTitle": "dr",
                        },
                        "clinicId": 20,
                        "clinic": "Klinika Swobodna",
                        "roomId": 30,
                        "scheduleId": 40,
                        "serviceVariantId": 4436,
                        "serviceVariantName": "Konsultacja ortopedyczna",
                        "isTelemedicine": False,
                        "isAdditional": False,
                        "preparationItems": [{"id": 99}],
                    }
                ],
            }
        ]
    },
}


def test_get_one_day_terms_parses_terms_and_correlation_id():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"}, _SAMPLE_TERMS_RESPONSE),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(service_id=4436, place=place, day=date(2026, 5, 8))

    assert response.correlation_id == "corr-abc"
    assert len(response.terms) == 1
    term = response.terms[0]
    assert term.doctor.first_name == "Jan"
    assert term.facility_name == "Klinika Swobodna"
    assert term.service_variant_id == 4436
    assert term.raw["preparationItems"] == [{"id": 99}]

    request = adapter.calls[1]
    assert "/NewPortal/terms/oneDayTerms" in request.url
    assert "searchPlace.id=5" in request.url
    assert "searchPlace.type=0" in request.url
    assert "serviceVariantId=4436" in request.url
    assert "searchDateFrom=2026-05-08" in request.url


def test_get_one_day_terms_empty_day_returns_no_terms():
    empty_response = {
        "correlationId": "corr-xyz",
        "termsForService": {"termsForDays": [{"day": "2026-05-08", "terms": []}]},
    }
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"}, empty_response),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(service_id=4436, place=place, day=date(2026, 5, 8))

    assert response.terms == []
    assert response.correlation_id == "corr-xyz"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_client_oneday.py -v
```

Expected: FAIL `AttributeError: ... 'get_one_day_terms'`

- [ ] **Step 3: Rozszerz `src/scrapper/client.py`**

Dodaj import na górze:

```python
from datetime import date, datetime
from urllib.parse import urlencode

from .models import Doctor, OneDayTermsResponse, Place, Term
```

Dodaj stałą:

```python
ONE_DAY_TERMS_URL = f"{BASE_URL}/NewPortal/terms/oneDayTerms"
```

Dodaj metody w klasie:

```python
    def get_one_day_terms(
        self, *, service_id: int, place: Place, day: date,
    ) -> OneDayTermsResponse:
        self.ensure_authenticated()
        self._propagate_xsrf()

        params = [
            ("searchPlace.id", str(place.id)),
            ("searchPlace.name", place.name),
            ("searchPlace.type", str(place.type)),
            ("serviceVariantId", str(service_id)),
            ("languageId", "10"),
            ("searchDateFrom", day.isoformat()),
            ("searchDatePreset", "14"),
            ("expectedTermsNumber", "1"),
            ("delocalized", "false"),
        ]
        url = f"{ONE_DAY_TERMS_URL}?{urlencode(params)}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return _parse_one_day_terms(data)


def _parse_one_day_terms(data: dict) -> OneDayTermsResponse:
    correlation_id = data.get("correlationId")
    terms: list[Term] = []
    days = ((data.get("termsForService") or {}).get("termsForDays") or [])
    for day_block in days:
        for raw_term in day_block.get("terms") or []:
            terms.append(_parse_term(raw_term))
    return OneDayTermsResponse(terms=terms, correlation_id=correlation_id, raw=data)


def _parse_term(raw: dict) -> Term:
    doc = raw.get("doctor") or {}
    return Term(
        date_time_from=datetime.fromisoformat(raw["dateTimeFrom"]),
        date_time_to=datetime.fromisoformat(raw["dateTimeTo"]),
        doctor=Doctor(
            id=doc.get("id", 0),
            first_name=doc.get("firstName", ""),
            last_name=doc.get("lastName", ""),
            academic_title=doc.get("academicTitle"),
        ),
        facility_id=raw.get("clinicId", 0),
        facility_name=raw.get("clinic", ""),
        room_id=raw.get("roomId", 0),
        schedule_id=raw.get("scheduleId", 0),
        service_variant_id=raw.get("serviceVariantId", 0),
        service_variant_name=raw.get("serviceVariantName", ""),
        is_telemedicine=bool(raw.get("isTelemedicine", False)),
        is_additional=bool(raw.get("isAdditional", False)),
        raw=raw,
    )
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_client_oneday.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/client.py tests/test_client_oneday.py
git commit -m "feat(scrapper): per-day oneDayTerms z parsowaniem terms+correlationId"
```

---

## Task 9: client.py — Save + LockTerm

**Files:**

- Modify: `src/scrapper/client.py`
- Test: `tests/test_client_booking.py`

**Referencja:** `docs/superpowers/curls/availability_save.sh` i `docs/superpowers/curls/lock_term.sh`. **Pełny body LockTerm zawiera `preparationItems` z odpowiedzi `oneDayTerms` 1:1** — bierzemy je z `term.raw`. Jeśli cURL pokazuje pola których spec nie wymienia (`isPoz`, `eReferralId` itp.) — zostawiamy je w body wprost z `term.raw`, nie filtrujemy.

- [ ] **Step 1: Utwórz failing test `tests/test_client_booking.py`**

```python
import json
import time
from datetime import datetime

import jwt as jwt_lib

from scrapper.client import LuxmedClient
from scrapper.models import Doctor, SearchContext, Term

from .test_client_login import _MockAdapter


def _jwt() -> str:
    return jwt_lib.encode({"exp": int(time.time()) + 600}, "s", algorithm="HS256")


def _term() -> Term:
    raw = {
        "dateTimeFrom": "2026-05-08T17:00:00",
        "dateTimeTo": "2026-05-08T17:30:00",
        "preparationItems": [{"id": 7, "name": "skierowanie"}],
        "isPoz": False,
        "isAdditional": False,
        "scheduleId": 40,
        "roomId": 30,
        "serviceVariantId": 4436,
        "clinicId": 20,
    }
    return Term(
        date_time_from=datetime(2026, 5, 8, 17, 0),
        date_time_to=datetime(2026, 5, 8, 17, 30),
        doctor=Doctor(id=11, first_name="J", last_name="K"),
        facility_id=20,
        facility_name="Klinika",
        room_id=30,
        schedule_id=40,
        service_variant_id=4436,
        service_variant_name="Ortopeda",
        is_telemedicine=False,
        is_additional=False,
        raw=raw,
    )


def _ctx() -> SearchContext:
    return SearchContext(
        process_id="proc-1",
        correlation_id="corr-1",
        search_parameters={"serviceVariantId": 4436, "cityId": 5},
    )


def test_save_availability_log_posts_json_with_correlation_and_process_ids():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"}, {"saved": True}),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    client.save_availability_log(_ctx())

    save_req = adapter.calls[1]
    assert save_req.method == "POST"
    assert save_req.url.endswith("/NewPortal/AvailabilityLog/Save")
    body = json.loads(save_req.body)
    assert body["correlationId"] == "corr-1"
    assert body["processId"] == "proc-1"
    assert body["searchParameters"] == {"serviceVariantId": 4436, "cityId": 5}


def test_lock_term_posts_full_payload_including_preparation_items():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"},
         {"value": {"temporaryReservationId": "res-42"}, "errors": []}),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    result = client.lock_term(_term(), _ctx())

    assert result.success is True
    assert result.temporary_reservation_id == "res-42"

    lock_req = adapter.calls[1]
    assert lock_req.url.endswith("/NewPortal/Reservation/LockTerm")
    body = json.loads(lock_req.body)
    assert body["correlationId"] == "corr-1"
    assert body["serviceVariantId"] == 4436
    assert body["roomId"] == 30
    assert body["scheduleId"] == 40
    assert body["clinicId"] == 20
    assert body["preparationItems"] == [{"id": 7, "name": "skierowanie"}]
    assert body["dateTimeFrom"] == "2026-05-08T17:00:00"
    assert body["dateTimeTo"] == "2026-05-08T17:30:00"


def test_lock_term_failure_returns_error_in_result():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"},
         {"value": None, "errors": [{"message": "Slot zajęty"}]}),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    result = client.lock_term(_term(), _ctx())

    assert result.success is False
    assert result.error == "Slot zajęty"
    assert result.temporary_reservation_id is None
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_client_booking.py -v
```

Expected: FAIL `AttributeError: ... 'save_availability_log'`

- [ ] **Step 3: Rozszerz `src/scrapper/client.py`**

Dodaj na górze import:

```python
from .models import Doctor, LockResult, OneDayTermsResponse, Place, SearchContext, Term
```

Dodaj stałe:

```python
SAVE_URL = f"{BASE_URL}/NewPortal/AvailabilityLog/Save"
LOCK_URL = f"{BASE_URL}/NewPortal/Reservation/LockTerm"
```

Dodaj metody w klasie:

```python
    def save_availability_log(self, ctx: SearchContext) -> None:
        self.ensure_authenticated()
        self._propagate_xsrf()
        body = {
            "correlationId": ctx.correlation_id,
            "processId": ctx.process_id,
            "searchParameters": ctx.search_parameters,
        }
        resp = self.session.post(SAVE_URL, json=body,
                                 headers={"Content-Type": "application/json"})
        resp.raise_for_status()

    def lock_term(self, term: Term, ctx: SearchContext) -> LockResult:
        self.ensure_authenticated()
        self._propagate_xsrf()
        body = _build_lock_term_body(term, ctx)
        resp = self.session.post(LOCK_URL, json=body,
                                 headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        errors = data.get("errors") or []
        if errors:
            err_msg = "; ".join(e.get("message", str(e)) for e in errors)
            return LockResult(success=False, temporary_reservation_id=None,
                              error=err_msg, raw=data)
        value = data.get("value") or {}
        reservation_id = value.get("temporaryReservationId")
        return LockResult(
            success=bool(reservation_id),
            temporary_reservation_id=reservation_id,
            error=None if reservation_id else "Brak temporaryReservationId w response",
            raw=data,
        )


def _build_lock_term_body(term: Term, ctx: SearchContext) -> dict:
    """Body LockTerm: bierzemy raw-term i mergujemy z context-id-ami.
    raw zawiera już preparationItems i pomocnicze pola których serwer wymaga."""
    body = dict(term.raw)
    body["correlationId"] = ctx.correlation_id
    body["processId"] = ctx.process_id
    body.setdefault("serviceVariantId", term.service_variant_id)
    body.setdefault("roomId", term.room_id)
    body.setdefault("scheduleId", term.schedule_id)
    body.setdefault("clinicId", term.facility_id)
    body.setdefault("dateTimeFrom", term.date_time_from.isoformat())
    body.setdefault("dateTimeTo", term.date_time_to.isoformat())
    return body
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_client_booking.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/client.py tests/test_client_booking.py
git commit -m "feat(scrapper): Save + LockTerm z forwardem raw preparationItems"
```

---

## Task 10: search.py — kryteria, matches, iter_days, find_matching_term, poll_loop

**Files:**

- Create: `src/scrapper/search.py`
- Test: `tests/test_search_filtering.py`
- Test: `tests/test_search_loop.py`

- [ ] **Step 1: Utwórz failing test `tests/test_search_filtering.py`**

```python
from datetime import date, datetime

from scrapper.models import Doctor, Place, Term
from scrapper.search import SearchCriteria, iter_days, matches


def _term(*, dt: datetime, doctor_last: str = "Kowalski",
          facility: str = "Klinika Swobodna") -> Term:
    return Term(
        date_time_from=dt,
        date_time_to=dt,
        doctor=Doctor(id=1, first_name="Jan", last_name=doctor_last),
        facility_id=20,
        facility_name=facility,
        room_id=1, schedule_id=1, service_variant_id=4436,
        service_variant_name="Ortopeda",
        is_telemedicine=False, is_additional=False, raw={},
    )


def _crit(**overrides) -> SearchCriteria:
    base = dict(
        service_id=4436,
        place=Place(id=5, name="Wrocław"),
        date_from=datetime(2026, 5, 5, 16, 0),
        date_to=datetime(2026, 5, 10, 19, 0),
    )
    base.update(overrides)
    return SearchCriteria(**base)


def test_matches_returns_true_when_inside_window():
    term = _term(dt=datetime(2026, 5, 7, 17, 0))
    assert matches(term, _crit()) is True


def test_matches_returns_false_when_before_window():
    term = _term(dt=datetime(2026, 5, 5, 14, 0))
    assert matches(term, _crit()) is False


def test_matches_returns_false_when_after_window():
    term = _term(dt=datetime(2026, 5, 10, 20, 0))
    assert matches(term, _crit()) is False


def test_matches_doctor_filter_case_insensitive():
    term = _term(dt=datetime(2026, 5, 7, 17, 0), doctor_last="KOWALSKI")
    assert matches(term, _crit(doctor_filter="kowal")) is True
    assert matches(term, _crit(doctor_filter="nowak")) is False


def test_matches_facility_filter_case_insensitive():
    term = _term(dt=datetime(2026, 5, 7, 17, 0), facility="Klinika Swobodna")
    assert matches(term, _crit(facility_filter="swobodna")) is True
    assert matches(term, _crit(facility_filter="legnicka")) is False


def test_iter_days_yields_dates_inclusive():
    crit = _crit(
        date_from=datetime(2026, 5, 5, 0, 0),
        date_to=datetime(2026, 5, 7, 23, 59),
    )
    days = list(iter_days(crit))
    assert days == [date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7)]


def test_iter_days_single_day():
    crit = _crit(
        date_from=datetime(2026, 5, 5, 16, 0),
        date_to=datetime(2026, 5, 5, 19, 0),
    )
    assert list(iter_days(crit)) == [date(2026, 5, 5)]
```

- [ ] **Step 2: Utwórz failing test `tests/test_search_loop.py`**

```python
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from scrapper.models import Doctor, OneDayTermsResponse, Place, Term
from scrapper.search import SearchCriteria, find_matching_term, poll_loop


def _term(dt: datetime) -> Term:
    return Term(
        date_time_from=dt, date_time_to=dt,
        doctor=Doctor(id=1, first_name="J", last_name="K"),
        facility_id=20, facility_name="C", room_id=1, schedule_id=1,
        service_variant_id=4436, service_variant_name="O",
        is_telemedicine=False, is_additional=False, raw={},
    )


def _crit() -> SearchCriteria:
    return SearchCriteria(
        service_id=4436,
        place=Place(id=5, name="Wrocław"),
        date_from=datetime(2026, 5, 5, 0, 0),
        date_to=datetime(2026, 5, 6, 23, 59),
    )


def test_find_matching_term_returns_first_match_across_days():
    client = MagicMock()
    client.get_one_day_terms.side_effect = [
        OneDayTermsResponse(terms=[], correlation_id="c1", raw={}),
        OneDayTermsResponse(
            terms=[_term(datetime(2026, 5, 6, 17, 0))], correlation_id="c2", raw={},
        ),
    ]

    found = find_matching_term(client, _crit())

    assert found is not None
    assert found.date_time_from == datetime(2026, 5, 6, 17, 0)
    assert client.get_one_day_terms.call_count == 2


def test_find_matching_term_returns_none_when_nothing_matches():
    client = MagicMock()
    client.get_one_day_terms.return_value = OneDayTermsResponse(
        terms=[], correlation_id="c", raw={},
    )
    assert find_matching_term(client, _crit()) is None


def test_poll_loop_returns_when_match_found_first_iteration():
    client = MagicMock()
    client.get_one_day_terms.return_value = OneDayTermsResponse(
        terms=[_term(datetime(2026, 5, 6, 17, 0))], correlation_id="c", raw={},
    )

    found = poll_loop(client, _crit(), sleep_min=0, sleep_max=0, max_iterations=1)

    assert found is not None


def test_poll_loop_raises_when_max_iterations_exceeded(monkeypatch):
    client = MagicMock()
    client.get_one_day_terms.return_value = OneDayTermsResponse(
        terms=[], correlation_id="c", raw={},
    )

    monkeypatch.setattr("scrapper.search.time.sleep", lambda _: None)

    with pytest.raises(TimeoutError):
        poll_loop(client, _crit(), sleep_min=0, sleep_max=0, max_iterations=3)

    assert client.get_one_day_terms.call_count >= 3
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
.venv/bin/pytest tests/test_search_filtering.py tests/test_search_loop.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'scrapper.search'`

- [ ] **Step 4: Implement `src/scrapper/search.py`**

```python
"""Kryteria + dopasowanie + pętla pollująca."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .client import LuxmedClient
from .models import Place, Term

logger = logging.getLogger(__name__)


@dataclass
class SearchCriteria:
    service_id: int
    place: Place
    date_from: datetime
    date_to: datetime
    doctor_filter: str | None = None
    facility_filter: str | None = None


def matches(term: Term, crit: SearchCriteria) -> bool:
    if term.date_time_from < crit.date_from or term.date_time_from > crit.date_to:
        return False
    if crit.doctor_filter:
        full = f"{term.doctor.first_name} {term.doctor.last_name}".casefold()
        if crit.doctor_filter.casefold() not in full:
            return False
    if crit.facility_filter:
        if crit.facility_filter.casefold() not in term.facility_name.casefold():
            return False
    return True


def iter_days(crit: SearchCriteria) -> Iterator[date]:
    current = crit.date_from.date()
    last = crit.date_to.date()
    while current <= last:
        yield current
        current += timedelta(days=1)


def find_matching_term(client: LuxmedClient, crit: SearchCriteria) -> Term | None:
    for day in iter_days(crit):
        response = client.get_one_day_terms(
            service_id=crit.service_id, place=crit.place, day=day,
        )
        for term in response.terms:
            if matches(term, crit):
                logger.info("Match: %s %s, %s", term.date_time_from.isoformat(),
                            term.doctor.full_name() if hasattr(term.doctor, "full_name") else "",
                            term.facility_name)
                return term
    return None


def poll_loop(
    client: LuxmedClient,
    crit: SearchCriteria,
    *,
    sleep_min: int = 30,
    sleep_max: int = 90,
    max_iterations: int | None = None,
) -> Term:
    iteration = 0
    while True:
        iteration += 1
        logger.info("Sweep #%d: %s → %s", iteration,
                    crit.date_from.isoformat(), crit.date_to.isoformat())
        found = find_matching_term(client, crit)
        if found:
            return found
        if max_iterations is not None and iteration >= max_iterations:
            raise TimeoutError(
                f"Brak slotów po {max_iterations} iteracjach"
            )
        delay = random.randint(sleep_min, sleep_max) if sleep_max > sleep_min else sleep_min
        logger.info("Brak slotów — śpię %ds", delay)
        time.sleep(delay)
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
.venv/bin/pytest tests/test_search_filtering.py tests/test_search_loop.py -v
```

Expected: 11 passed (7 + 4)

- [ ] **Step 6: Commit**

```bash
git add src/scrapper/search.py tests/test_search_filtering.py tests/test_search_loop.py
git commit -m "feat(scrapper): SearchCriteria + matches + per-day poll loop"
```

---

## Task 11: booking.py — Save → LockTerm orchestration

**Files:**

- Create: `src/scrapper/booking.py`
- Test: `tests/test_booking.py`

- [ ] **Step 1: Utwórz failing test `tests/test_booking.py`**

```python
from datetime import datetime
from unittest.mock import MagicMock

from scrapper.booking import lock
from scrapper.models import Doctor, LockResult, SearchContext, Term


def _term() -> Term:
    return Term(
        date_time_from=datetime(2026, 5, 8, 17, 0),
        date_time_to=datetime(2026, 5, 8, 17, 30),
        doctor=Doctor(id=1, first_name="J", last_name="K"),
        facility_id=20, facility_name="C", room_id=1, schedule_id=1,
        service_variant_id=4436, service_variant_name="O",
        is_telemedicine=False, is_additional=False, raw={},
    )


def test_lock_calls_save_then_lock_term_in_order():
    client = MagicMock()
    client.lock_term.return_value = LockResult(
        success=True, temporary_reservation_id="r-1", error=None, raw={},
    )
    ctx = SearchContext(process_id="p", correlation_id="c", search_parameters={})

    result = lock(client, _term(), ctx)

    assert result.success is True
    client.save_availability_log.assert_called_once_with(ctx)
    client.lock_term.assert_called_once()
    # Save before LockTerm
    save_call_idx = client.method_calls.index(client.save_availability_log.call_args_list[0])
    lock_call_idx = client.method_calls.index(client.lock_term.call_args_list[0])
    # Method-call ordering in mock_calls:
    names = [c[0] for c in client.mock_calls]
    assert names.index("save_availability_log") < names.index("lock_term")


def test_lock_returns_failure_when_lockterm_fails():
    client = MagicMock()
    client.lock_term.return_value = LockResult(
        success=False, temporary_reservation_id=None, error="Zajęty", raw={},
    )
    ctx = SearchContext(process_id="p", correlation_id="c", search_parameters={})

    result = lock(client, _term(), ctx)

    assert result.success is False
    assert result.error == "Zajęty"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_booking.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/scrapper/booking.py`**

```python
"""Save → LockTerm flow. Cienki orchestrator nad LuxmedClient."""

from __future__ import annotations

import logging

from .client import LuxmedClient
from .models import LockResult, SearchContext, Term

logger = logging.getLogger(__name__)


def lock(client: LuxmedClient, term: Term, ctx: SearchContext) -> LockResult:
    logger.info("Save preflight (correlationId=%s)", ctx.correlation_id)
    client.save_availability_log(ctx)
    logger.info("LockTerm: %s, %s, %s",
                term.date_time_from.isoformat(),
                term.doctor.full_name(),
                term.facility_name)
    return client.lock_term(term, ctx)
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_booking.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/booking.py tests/test_booking.py
git commit -m "feat(scrapper): booking flow Save→LockTerm"
```

---

## Task 12: notify.py — Telegram

**Files:**

- Create: `src/scrapper/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: Utwórz failing test `tests/test_notify.py`**

```python
from unittest.mock import MagicMock, patch

from scrapper.notify import TelegramNotifier


def test_send_calls_telegram_api_with_correct_payload():
    notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")
    with patch("scrapper.notify.requests.post") as post:
        post.return_value = MagicMock(status_code=200, ok=True)
        notifier.send("Wizyta zarezerwowana")

    post.assert_called_once()
    url = post.call_args.args[0]
    assert "api.telegram.org/bot123:abc/sendMessage" in url
    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "42"
    assert payload["text"] == "Wizyta zarezerwowana"


def test_send_swallows_network_errors_and_logs(caplog):
    import logging

    notifier = TelegramNotifier(bot_token="t", chat_id="c")
    with patch("scrapper.notify.requests.post") as post:
        post.side_effect = ConnectionError("brak netu")
        with caplog.at_level(logging.WARNING, logger="scrapper.notify"):
            notifier.send("hello")

    assert any("Telegram" in r.getMessage() for r in caplog.records)


def test_send_logs_warning_on_non_200():
    import logging

    notifier = TelegramNotifier(bot_token="t", chat_id="c")
    with patch("scrapper.notify.requests.post") as post:
        post.return_value = MagicMock(status_code=400, ok=False, text="bad")
        with caplog := __import__("_pytest.logging").logging.LogCaptureHandler():
            pass
    # Wystarczy że nie wyrzuca — szczegółowy log-check w test_logging.
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_notify.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/scrapper/notify.py`**

```python
"""Telegram bot notifier — best-effort, nie blokuje flow."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Telegram non-2xx: %s %s", resp.status_code, resp.text)
        except Exception as exc:  # ConnectionError, Timeout, etc.
            logger.warning("Telegram send failed: %s", exc)
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_notify.py -v
```

Expected: 3 passed (3rd test is no-op, will pass)

- [ ] **Step 5: Commit**

```bash
git add src/scrapper/notify.py tests/test_notify.py
git commit -m "feat(scrapper): TelegramNotifier (best-effort send)"
```

---

## Task 13: cli.py — argparse + sub-commands

**Files:**

- Create: `src/scrapper/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Utwórz failing test `tests/test_cli.py`**

```python
import pytest

from scrapper.cli import build_parser, parse_datetime


def test_parse_datetime_accepts_yyyy_mm_dd_hh_mm():
    dt = parse_datetime("2026-05-08 17:00")
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 8
    assert dt.hour == 17
    assert dt.minute == 0


def test_parse_datetime_invalid_raises():
    with pytest.raises(ValueError):
        parse_datetime("nie-data")


def test_search_parser_requires_either_service_id_or_name():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--city", "Wrocław",
                           "--from", "2026-05-05 16:00",
                           "--to", "2026-05-05 19:00"])


def test_search_parser_accepts_service_id():
    parser = build_parser()
    args = parser.parse_args([
        "search", "--service-id", "4436",
        "--city", "Wrocław",
        "--from", "2026-05-05 16:00",
        "--to", "2026-05-05 19:00",
    ])
    assert args.subcommand == "search"
    assert args.service_id == 4436
    assert args.city == "Wrocław"
    assert args.no_lock is False
    assert args.once is False


def test_search_parser_no_lock_and_once_flags():
    parser = build_parser()
    args = parser.parse_args([
        "search", "--service-name", "Ortopeda",
        "--city", "Wrocław",
        "--from", "2026-05-05 16:00",
        "--to", "2026-05-05 19:00",
        "--no-lock", "--once",
    ])
    assert args.no_lock is True
    assert args.once is True


def test_services_subcommand():
    parser = build_parser()
    args = parser.parse_args(["services", "--query", "ortop"])
    assert args.subcommand == "services"
    assert args.query == "ortop"


def test_smoke_subcommand():
    parser = build_parser()
    args = parser.parse_args(["smoke"])
    assert args.subcommand == "smoke"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/scrapper/cli.py`**

```python
"""CLI: scrapper search / services / smoke."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .booking import lock
from .catalog import find_service_by_id, find_services_by_name
from .client import AuthError, LuxmedClient
from .config import Settings, load_settings
from .logging_setup import setup_logging
from .models import Place, SearchContext
from .notify import TelegramNotifier
from .search import SearchCriteria, find_matching_term, poll_loop

logger = logging.getLogger(__name__)


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrapper", description="Luxmed scrapper")
    parser.add_argument("--debug", action="store_true",
                        help="Verbose logging do ~/.luxmed-scrapper/scrapper.log")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # search
    search = sub.add_parser("search", help="Pollowanie + LockTerm")
    svc = search.add_mutually_exclusive_group(required=True)
    svc.add_argument("--service-id", type=int)
    svc.add_argument("--service-name", type=str)
    search.add_argument("--city", required=True)
    search.add_argument("--from", dest="date_from", required=True, type=parse_datetime)
    search.add_argument("--to", dest="date_to", required=True, type=parse_datetime)
    search.add_argument("--doctor", default=None)
    search.add_argument("--facility", default=None)
    search.add_argument("--once", action="store_true",
                        help="Jeden sweep (bez pętli)")
    search.add_argument("--no-lock", action="store_true",
                        help="Tylko alert, bez LockTerm")
    search.add_argument("--max-iterations", type=int, default=None)

    # services
    services = sub.add_parser("services", help="Listuj services")
    services.add_argument("--query", default=None)

    # smoke
    sub.add_parser("smoke", help="End-to-end smoke (login + groups + 1 search)")

    return parser


CITY_IDS = {
    "warszawa": 1, "kraków": 2, "krakow": 2, "łódź": 3, "lodz": 3,
    "wrocław": 5, "wroclaw": 5, "poznań": 6, "poznan": 6,
    "gdańsk": 9, "gdansk": 9, "katowice": 7, "lublin": 8,
}


def _resolve_place(city: str) -> Place:
    key = city.casefold()
    if key in CITY_IDS:
        return Place(id=CITY_IDS[key], name=city)
    raise SystemExit(f"Nieznane miasto '{city}'. Dodaj do CITY_IDS w cli.py.")


def _resolve_service(client: LuxmedClient, args: argparse.Namespace) -> int:
    groups = client.get_service_groups()
    if args.service_id:
        match = find_service_by_id(groups, args.service_id)
        if not match:
            raise SystemExit(f"Service id {args.service_id} nie istnieje")
        logger.info("Service: %s — %s", match.service_id, match.name)
        return match.service_id
    matches = find_services_by_name(groups, args.service_name)
    if not matches:
        raise SystemExit(f"Brak service pasującego do '{args.service_name}'")
    if len(matches) > 1:
        print("Wiele dopasowań — sprecyzuj przez --service-id:", file=sys.stderr)
        for m in matches:
            print(f"  {m.service_id}  {m.name}  ({' / '.join(m.path)})", file=sys.stderr)
        raise SystemExit(2)
    logger.info("Service: %s — %s", matches[0].service_id, matches[0].name)
    return matches[0].service_id


def _cmd_search(args: argparse.Namespace, settings: Settings) -> int:
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()

    service_id = _resolve_service(client, args)
    place = _resolve_place(args.city)
    crit = SearchCriteria(
        service_id=service_id, place=place,
        date_from=args.date_from, date_to=args.date_to,
        doctor_filter=args.doctor, facility_filter=args.facility,
    )

    if args.once:
        term = find_matching_term(client, crit)
        if not term:
            logger.info("Brak slotów w zakresie")
            return 0
    else:
        term = poll_loop(client, crit, max_iterations=args.max_iterations)

    if args.no_lock:
        logger.info("Slot znaleziony (no-lock): %s, %s, %s",
                    term.date_time_from.isoformat(),
                    term.doctor.full_name(),
                    term.facility_name)
        return 0

    import uuid
    ctx = SearchContext(
        process_id=str(uuid.uuid4()),
        correlation_id=None,  # dopisuje się z ostatniego oneDayTerms — ale tu mamy term, ale bez ctx
        search_parameters={
            "serviceVariantId": service_id,
            "cityId": place.id,
        },
    )
    # Re-fetch correlationId dla danego dnia (LockTerm wymaga niedawnego)
    response = client.get_one_day_terms(
        service_id=service_id, place=place, day=term.date_time_from.date(),
    )
    ctx.correlation_id = response.correlation_id

    result = lock(client, term, ctx)
    if not result.success:
        logger.error("LockTerm fail: %s", result.error)
        return 1

    msg = (
        f"<b>Wizyta zarezerwowana (5-10 min)</b>\n"
        f"{term.doctor.full_name()}\n"
        f"{term.date_time_from.strftime('%Y-%m-%d %H:%M')}\n"
        f"{term.facility_name}\n"
        f"https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/MyVisits"
    )
    logger.info("Slot zarezerwowany: %s", result.temporary_reservation_id)
    if settings.telegram_enabled:
        TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id).send(msg)
    return 0


def _cmd_services(args: argparse.Namespace, settings: Settings) -> int:
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()
    groups = client.get_service_groups()
    matches = (find_services_by_name(groups, args.query)
               if args.query else [])
    if not args.query:
        print("Podaj --query, np. --query ortop", file=sys.stderr)
        return 2
    if not matches:
        print(f"Brak service pasującego do '{args.query}'")
        return 0
    for m in matches:
        print(f"{m.service_id}\t{m.name}\t({' / '.join(m.path)})")
    return 0


def _cmd_smoke(args: argparse.Namespace, settings: Settings) -> int:
    from datetime import date
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()
    groups = client.get_service_groups()
    if not groups:
        logger.error("serviceVariantsGroups puste")
        return 1
    logger.info("Groups OK (%d top-level)", len(groups))

    first_service_id = None
    def _first_leaf(nodes):
        for n in nodes:
            children = n.get("children") or []
            if not children and n.get("id"):
                return n["id"]
            found = _first_leaf(children)
            if found:
                return found
        return None
    first_service_id = _first_leaf(groups)
    if not first_service_id:
        logger.error("Brak leaf-service w groups")
        return 1

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(
        service_id=first_service_id, place=place, day=date.today(),
    )
    logger.info("oneDayTerms OK: %d terms, correlationId=%s",
                len(response.terms), response.correlation_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_file = Path.home() / ".luxmed-scrapper" / "scrapper.log" if args.debug else None
    setup_logging(verbose=args.debug, log_file=log_file)

    try:
        settings = load_settings()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    try:
        if args.subcommand == "search":
            return _cmd_search(args, settings)
        if args.subcommand == "services":
            return _cmd_services(args, settings)
        if args.subcommand == "smoke":
            return _cmd_smoke(args, settings)
    except AuthError as exc:
        logger.error("Auth: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Przerwane przez użytkownika")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test — expect PASS**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 7 passed

- [ ] **Step 5: Sprawdź entry point**

```bash
.venv/bin/scrapper --help
.venv/bin/scrapper search --help
.venv/bin/scrapper services --help
```

Expected: każde wypisuje pomoc, exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/scrapper/cli.py tests/test_cli.py
git commit -m "feat(scrapper): CLI z search/services/smoke"
```

---

## Task 14: Skasuj stary kod (jednym commitem)

**Files:**

- Delete: `main.py`, `flaskServer.py`, `tools.py`, `test_scrapper.py`, `config.py` (root)
- Delete: `templates/`, `static/`, `__pycache__/`, `responses/` (jeśli istnieje)

- [ ] **Step 1: Sprawdź że nic z nowego kodu nie importuje starych modułów**

```bash
grep -rn "from main\|import main\|from tools\|import tools\|from flaskServer\|import flaskServer\|^import config\b" src/ tests/ || echo "OK — no references"
```

Expected: `OK — no references`. Jeśli coś znajdzie — STOP, napraw przed kasowaniem.

- [ ] **Step 2: Usuń pliki**

```bash
rm -f main.py flaskServer.py tools.py test_scrapper.py config.py
rm -rf templates/ static/ __pycache__/
rm -rf responses/ 2>/dev/null || true
```

- [ ] **Step 3: Sprawdź że testy nadal przechodzą**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_smoke.py
```

Expected: wszystkie przechodzą (smoke pomijany jeśli brak `.env`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(scrapper): skasuj legacy main/flask/tools, plaintext config.py"
```

---

## Task 15: smoke test (real network)

**Files:**

- Create: `tests/test_smoke.py`

- [ ] **Step 1: Implement `tests/test_smoke.py`**

```python
"""End-to-end smoke. Wymaga .env z LUXMED_EMAIL/LUXMED_PASSWORD.
Uruchom: pytest tests/test_smoke.py -v -s -m smoke
albo: scrapper smoke
"""

from datetime import date

import pytest

from scrapper.client import LuxmedClient
from scrapper.config import load_settings
from scrapper.models import Place


@pytest.mark.smoke
def test_smoke_login_groups_search(env_loaded):
    settings = load_settings(load_dotenv_file=False)
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)

    client.login()
    assert client.is_authenticated()

    groups = client.get_service_groups()
    assert isinstance(groups, list)
    assert len(groups) > 0

    def _first_leaf(nodes):
        for n in nodes:
            children = n.get("children") or []
            if not children and n.get("id"):
                return n["id"]
            found = _first_leaf(children)
            if found:
                return found
        return None
    service_id = _first_leaf(groups)
    assert service_id is not None

    response = client.get_one_day_terms(
        service_id=service_id, place=Place(id=5, name="Wrocław"), day=date.today(),
    )
    assert response is not None
    # terms może być pusty (brak slotów dziś) — to OK, smoke chce tylko 200+JSON
```

- [ ] **Step 2: Zarejestruj marker smoke w pyproject**

Edytuj `pyproject.toml`, dopisz pod `[tool.pytest.ini_options]`:

```toml
markers = ["smoke: end-to-end test wymagający .env i sieci"]
```

- [ ] **Step 3: Uruchom smoke (wymaga `.env`)**

```bash
.venv/bin/pytest tests/test_smoke.py -v -s
```

Expected:

- Jeśli brak `.env` → SKIP z komunikatem.
- Jeśli `.env` jest → PASS (login + groups + oneDayTerms zwracają sensowne dane).

Jeśli FAIL — to sygnał że Luxmed znów coś zmienił. To jest cel smoke'a.

- [ ] **Step 4: Commit**

```bash
git add tests/test_smoke.py pyproject.toml
git commit -m "test(scrapper): smoke end-to-end (login+groups+oneDayTerms)"
```

---

## Task 16: README + .env wireup

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Nadpisz `README.md`**

````markdown
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
````

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

Per-day search: nie 14-dniowe okno, tylko iteracja dzień-po-dniu (jeden GET per dzień).
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

````

- [ ] **Step 2: Sprawdź że README renderuje się sensownie**

```bash
cat README.md | head -40
````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(scrapper): README z setup + użyciem + architekturą"
```

---

## Task 17: Manualna walidacja end-to-end (acceptance)

**Cel:** sprawdzić acceptance criteria ze speca: scrapper potrafi zlockować slot, Telegram dostaje wiadomość, smoke przechodzi.

- [ ] **Step 1: Setup `.env` (jeśli jeszcze nie ma)**

Adrian sam wypełnia plaintext credentials. Potwierdza w czacie że plik jest.

- [ ] **Step 2: Smoke test**

```bash
.venv/bin/scrapper smoke
```

Expected: `oneDayTerms OK: ... terms, correlationId=...`. Exit 0.

- [ ] **Step 3: Listuj service'y**

```bash
.venv/bin/scrapper services --query fizjoterapeuta
```

Expected: lista z >0 wpisami (fizjoterapeuta = dużo wolnych slotów = łatwy test booking).

- [ ] **Step 4: Search bez locka — jeden sweep**

```bash
.venv/bin/scrapper search \
  --service-name "fizjoterapeuta" \
  --city Wrocław \
  --from "$(date +%Y-%m-%d) 08:00" \
  --to "$(date -d '+3 days' +%Y-%m-%d) 20:00" \
  --once --no-lock
```

Expected: log "Slot znaleziony (no-lock): ..." albo "Brak slotów w zakresie".

- [ ] **Step 5: Pełny e2e — search + lock + Telegram (na fizjoterapeucie)**

```bash
.venv/bin/scrapper search \
  --service-name "fizjoterapeuta" \
  --city Wrocław \
  --from "$(date +%Y-%m-%d) 08:00" \
  --to "$(date -d '+3 days' +%Y-%m-%d) 20:00" \
  --once
```

Expected:

- log "Slot zarezerwowany: res-..."
- Telegram message dotrze do chat_id
- W przeglądarce: `https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/MyVisits` pokazuje pending reservation

- [ ] **Step 6: Pozwól wygasnąć (lub potwierdź klikiem)**

5-10 minut nic nie rób → slot się sam zwolni. (Albo Adrian klika confirm jeśli realnie chce wizytę.)

- [ ] **Step 7: Cleanup security**

Adrian:

- Loguje się do Luxmed Web
- Profil → Zmień hasło → ustawia nowe
- Profil → Wyloguj wszystkie urządzenia
- Aktualizuje `LUXMED_PASSWORD` w `.env` na nowe

- [ ] **Step 8: Final commit (jeśli były tweaki podczas walidacji)**

```bash
git status
# jeśli czysto — koniec, nic nie commituj
# jeśli były poprawki — commit per fix
```

---

## Acceptance criteria (ze speca)

- [ ] `scrapper search` znajduje wizytę i lockuje (Task 17 step 5).
- [ ] Telegram dostaje powiadomienie z linkiem (Task 17 step 5).
- [ ] `scrapper smoke` przechodzi (Task 17 step 2 + Task 15).
- [ ] `scrapper services --query "ortop"` zwraca matche (Task 17 step 3).
- [ ] Stary kod (`main.py`, `flaskServer.py`, `tools.py`, `test_scrapper.py`, `templates/`, `static/`, root `config.py`) skasowany jednym commitem (Task 14).
- [ ] `.env.example` w repo, `.env` w `.gitignore` (Task 0 + Task 2).
- [ ] README zaktualizowany (Task 16).
- [ ] Brak `print()` w kodzie produkcyjnym poza `cli.py` (verify: `grep -rn "print(" src/scrapper/ | grep -v cli.py` → 0 hitów).
- [ ] Adrian zmienił hasło i wylogował sesje (Task 17 step 7).

---

## Self-review notes

**Spec coverage:** każda sekcja speca ma task — login (T6), oneDayTerms (T8), Save+LockTerm (T9), per-day pollowanie (T10), Telegram (T12), CLI (T13), smoke (T15), kasowanie legacy (T14), README (T16), security cleanup (T17 step 7).

**Niepewności (znane):**

1. `Pact:` header — pominięty w T6/T8 zgodnie ze spec'em ("hipoteza: telemetria"). Jeśli oneDayTerms da 400/403 podczas T17 → dodaj header ze stałą wartością z `docs/superpowers/curls/one_day_terms.sh` w `client.py` w `DEFAULT_HEADERS`.
2. URL do confirm w Telegramie: linkujemy do `MyVisits`. Jeśli okaże się że jest dedykowana strona "potwierdź rezerwację tymczasową" — dopisać po obserwacji w T17.
3. CityIDs w `cli.py` — hardcoded mapa kilku miast. Jeśli Adrian potrzebuje miasta nieobsługiwanego → dodaj do mapy ręcznie albo wprowadź `scrapper cities` (poza scope tego planu).
4. `correlationId` re-fetch w `_cmd_search` (T13): wołamy `oneDayTerms` drugi raz dla tego samego dnia żeby dostać świeży correlationId tuż przed Save. Może być racey (slot zniknie między fetchami) — w T17 obserwuj, jeśli problem → trzymać correlationId z pierwszego fetchu w `find_matching_term` (refactor po walidacji).

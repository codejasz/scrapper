# RECON_REPORT — Luxmed scrapper, Faza 1

**Data:** 2026-04-29
**Wykonawca:** Claude Code (recon read-only, brak modyfikacji `main.py` / `flaskServer.py` / `tools.py` / `test_scrapper.py`)
**Repo:** `/home/adrian/privatespace/repositories/scrapper/` (master, ostatni commit `bc13543` z 2020-12-11)
**Konto Luxmed:** `adrian.kodjasz@gmail.com` (świadomie zaakceptowane ryzyko ekspozycji hasła w transkrypcie sesji)
**Outputs raw:** `/tmp/luxmed_recon_outputs/` (HTML/JSON dumps, do analizy)
**Bookingu nie wywołano** — `getToken`, `saveTerm`, `lockTerm`, `confirmVisit` pominięte zgodnie z planem.

---

## 1. Streszczenie

Portal Luxmed nadal istnieje i nadal pozwala się zalogować, ale **architektonicznie się zmienił**: stary scrapper był pisany pod stronę server-side renderowaną z `<form id="loginForm">` i HTML responses, a obecny portal to **Angular SPA z JWT API**. Login działa (zwraca JWT), endpoint `serviceVariantsGroups` działa i zwraca dane zgodne z parserem (3 kategorie, 132+156+3 examy). **Endpoint wyszukiwania `terms/index` zwraca HTTP 500** — prawdopodobnie wymaga teraz nagłówka `Authorization: Bearer <jwt>` zamiast cookie sesji ASP.NET, na której oparty jest obecny kod. Skala pracy w Fazie 2: **średnia/duża** — to nie naprawa kosmetyczna, tylko przepisanie warstwy autoryzacji + parsowania loginu pod nowy model JWT, oraz zdiagnozowanie nowego kontraktu API dla searcha (najprawdopodobniej z DevTools przeglądarki, bo skrypt nie odgadnie nowego formatu).

---

## 2. Wynik per krok

| #   | Krok                    | Status      | Notatka                                                                                                                                                                                                                                                                                                                                                                                                      |
| --- | ----------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | `getMainPage()`         | DZIAŁA, ALE | HTTP 200 + redirect 302 → `/NewPortal/Page/Account/Login`. Stary marker `id="loginForm"` **nie istnieje** — strona to teraz Angular SPA, brak `<form>` w HTML. Cookie inicjalne ustawione poprawnie.                                                                                                                                                                                                         |
| 2   | `getLogin()`            | DZIAŁA, ALE | HTTP 200, `Content-Type: application/json`. Login **zaakceptowany** (`succeded: true`), zwraca JWT z roszczeniami. Cookie autoryzacyjne ustawione (`Authorization-Token`, `LXToken`, `RefreshToken`). **ALE** stary regex na HTML-u (`dropdown".*?"name">...`) zwraca 0 dopasowań — bo response to JSON, nie HTML. W obecnym kodzie ten brak wywoła `IndexError: list index out of range` na `findall()[0]`. |
| 3   | `getGroupsIds()`        | OK          | HTTP 200, JSON, 3 top-level kategorie (`Konsultacje`, `Badania`, `Inne usługi`) z 291 examami łącznie. **`parseVarieties()` parsuje to bez błędu.** Struktura odpowiedzi pasuje do obecnego parsera — to jedyna część flow która nie wymaga zmian.                                                                                                                                                           |
| 4   | `searchVisits(exam_id)` | **PĘKA**    | HTTP **500 Internal Server Error** dla wszystkich testowanych examId (8904 — Chirurg stomatolog, 4436 — Ortopeda z `debug_dict`, 6904 — Ortodonta). Response to generic error page Luxmedu (`<title>LUX MED - Błąd</title>`, `"Coś poszło nie tak"`). Endpoint odpowiada, ale odrzuca wszystkie naszze żądania.                                                                                              |

**Legenda:** OK = działa zgodnie z oczekiwaniem · DZIAŁA, ALE = endpoint odpowiada ale parser/kod się rozjeżdża · PĘKA = endpoint zwraca błąd

---

## 3. Detale techniczne

### Krok 1 — `getMainPage()`

- **Request:** `GET https://portalpacjenta.luxmed.pl/PatientPortal/Account/LogOn`
- **Final URL po redirect:** `/PatientPortal/NewPortal/Page/Account/Login` (302)
- **Response:** HTTP 200, `text/html`, 14 734 B
- **Stary kontrakt:** kod sprawdza tylko `status == 200` i zapisuje HTML w DEV_MODE — to nadal działa. Ale `getLogin` później używa wyniku do regex-a, który już nie zadziała.
- **Co się zmieniło:** strona to teraz **Angular SPA**. Zero elementów `<form>` w HTML. Login dzieje się prawdopodobnie przez JS callem do `/Account/LogIn` (który jednocześnie obsługuje też nasz POST jak widać w kroku 2).

**Dump:** `/tmp/luxmed_recon_outputs/01_main_page.html`

### Krok 2 — `getLogin()`

- **Request:** `POST /PatientPortal/Account/LogIn` z body `Login=...&Password=...`
- **Response:** HTTP 200, `application/json`, 2 022 B
- **Body (skrót):**
  ```json
  {
    "succeded": true,
    "errorMessage": null,
    "showCannotLogin": false,
    "returnUrl": null,
    "token": "eyJhbGciOiJIUzI1NiIs..." // JWT
  }
  ```
- **Cookies ustawione po zalogowaniu:** `RefreshToken`, `Authorization-Token`, `UserAdditionalInfo`, `LXCookieMonit`, `GlobalLang`, `LXToken`. Wskazuje że Luxmed wystawia zarówno cookie sesyjne jak i JWT bearer token.
- **JWT zawiera:** `unique_name`, `given_name`, `family_name`, `lx_role: Beneficiary`, listę feature flags, `nbf`/`exp` (token ważny 10 min — `exp - iat = 600s`).

**Co psuje stary kod:**

```python
# main.py:107-110
username_pattern = re.compile(
    'dropdown[\'\"].*?[\'\"]name[\'\"]>([A-Z\s]+)<', re.S)
username = username_pattern.findall(response.text)[0]  # IndexError tutaj
```

Regex szuka HTML elementu z imieniem zalogowanego usera w dropdown menu — bo dawniej Luxmed po loginie zwracał HTML strony głównej z user-menu. Teraz zwraca JSON.

**Hipoteza naprawy (Faza 2):**

- Wymienić parsowanie na `response.json()['succeded']` jako check, a username brać z `given_name + family_name` w decoded JWT (lub z innego endpointu profilowego).

**Dump:** `/tmp/luxmed_recon_outputs/02_after_login.html` (mimo nazwy `.html` — w środku jest JSON)

### Krok 3 — `getGroupsIds()`

- **Request:** `GET /PatientPortal/NewPortal/Dictionary/serviceVariantsGroups` z headerami `X-Requested-With: XMLHttpRequest`, `Referer: .../Reservation/Search`
- **Response:** HTTP 200, JSON list, 200 230 B
- **Struktura:** 3 kategorie top-level (`Konsultacje`, `Badania`, `Inne usługi`), każda z `children` — wpisy mają `id`, `name`, `type`, `children`, `isTelemedicine`, `isVideoConsultation`, `isPoz`, `paymentType`.
- **Parser:** `LuxmedParser.parseVarieties()` przerobił to na 3 kategorie z `examList`: 132 + 156 + 3 = 291 examów łącznie. **Bez błędu.**

**Drobna obserwacja (out of scope dla Fazy 1, do potencjalnej naprawy):** parser spłaszcza 3-poziomową hierarchię (`Stomatologia → Chirurg stomatolog`) do 2 poziomów, gubiąc nazwę grupy pośredniej. Działa, ale UX rozumienia listy w UI cierpi.

**Dumps:** `03_groups.json` (raw), `03_varieties.json` (po parserze)

### Krok 4 — `searchVisits()` ⚠️ Główny problem

- **Request:** `GET /PatientPortal/NewPortal/terms/index?serviceVariantId=...&cityId=5&languageId=10&searchDateFrom=...&searchDateTo=...&processId=<uuid>&...`
- **Response:** HTTP **500 Internal Server Error**, `text/html`, 3 358 B
- **Body:** generic Luxmed error page:
  ```html
  <title>LUX MED - Błąd</title>
  ...
  <div class="error-page-title">Coś poszło nie tak</div>
  <div class="error-page-content">
    Nie możemy teraz wyświetlić tej strony. Przepraszamy za utrudnienia.
  </div>
  ```
- **Testowane examIds:** 8904 (Chirurg stomatolog), 4436 (Ortopeda — oryginalna hardcoded wartość z `debug_dict`), 6904 (Ortodonta) — **wszystkie 500**.
- **Cookies w sesji w momencie wywołania:** kompletny zestaw poautoryzacyjny (`Authorization-Token`, `LXToken`, `RefreshToken`, `ASP.NET_SessionId`) + WAF cookies (`incap_ses_*`, `visid_incap_*` — Imperva/Incapsula).

**Hipotezy (od najbardziej do najmniej prawdopodobnej):**

1. **Wymagany `Authorization: Bearer <jwt>` header** — Luxmed migrował z cookie session na JWT bearer dla NewPortal API. Nasz kod ustawia tylko cookies, ale endpoint nie patrzy już na cookie; szuka headera Authorization. **Najbardziej prawdopodobne** biorąc pod uwagę że login wystawia JWT a kod go ignoruje.

2. **Zmieniona struktura parametrów** — być może `cityId` to teraz `regionId`, albo `processId` musi być przekazany inaczej, albo wymagany jest jakiś nowy `correlationId` ustawiony wcześniejszym GET-em.

3. **Endpoint wymaga preflight calla** — np. trzeba najpierw zawołać `getToken` (XSRF) przed search-em, albo jakiś inny endpoint inicjalizujący który stary kod robi dopiero przy bookingu.

4. **Anti-bot/WAF blokada** — Imperva może identyfikować ten request jako bot i zwracać generyczne 500. Mniej prawdopodobne, bo `getGroupsIds` przeszedł bez problemu z dokładnie tymi samymi headerami sesyjnymi.

**Propozycja kierunku diagnozy w Fazie 2:**

- Zalogować się ręcznie w przeglądarce na luxmed.pl, otworzyć DevTools → Network, wyszukać losową wizytę i **skopiować dokładny request** (Copy as cURL).
- Porównać: URL endpointu, query params, **wszystkie** request headers, cookie. Najprawdopodobniej zobaczymy `Authorization: Bearer <jwt>` w prawdziwym requestzie.
- Następnie dostosować `searchVisits` do nowego kontraktu — to może być proste (dodać 1 header) lub poważne (zmieniony URL + struktura params).

**Dump:** `04_visits_500_error.html`

---

## 4. Rekomendacja dla Fazy 2

**Skala pracy: średnia.** To nie jest "fix kilku linijek" ani "rewrite from scratch". Plan powinien obejmować:

### Etap A — diagnostyka API (1 sesja)

1. **Capture realnego ruchu z przeglądarki** dla loginu, search i bookingu (DevTools / mitmproxy / Playwright record). Bez tego dalsze gadanie to zgadywanie. Booking obserwujemy ale nie wykonujemy — można zatrzymać się przed `lockTerm` lub testować na slocie który zaraz wygaśnie.
2. **Udokumentować nowy kontrakt:** endpointy URL-e, headers (zwłaszcza Authorization), struktura query/body params, format JSON odpowiedzi.

### Etap B — minimalna reanimacja (1-2 sesje)

3. **Naprawić `getLogin`:** parsować JSON response, wyciągnąć JWT, zapisać go jako Bearer token w `self.session.headers`. Username brać z JWT lub z dodatkowego endpointu profilowego.
4. **Naprawić `searchVisits`:** dostosować do nowego kontraktu — minimum dodać `Authorization` header, prawdopodobnie też tweakować params.
5. **Sprawdzić `parseVisits`:** struktura JSON dla termów może się zmienić — to zobaczymy dopiero gdy search zwróci 200.
6. **Booking flow:** `getToken` + `lockTerm` + `confirmVisit` — najprawdopodobniej też wymagają nowych headerów; to weryfikujemy świadomie i ostrożnie (idealnie na gabinecie który mamy zarezerwować świadomie).

### Etap C — sanityzacja kodu (jedna sesja, mogą być równolegle do Etapu B)

7. Naprawa znanych bugów: `searchVisits()` bez argumentu w `main.py:502`, `Luxmed` vs `LuxmedRequester` w teście, `SyntaxWarning` na `\s` w regex, niedokończony dekorator `request_printer`.
8. Dodanie `requirements.txt` (4 paczki: requests, flask, simplejson, python-dateutil).
9. Dodanie wpisów do `.gitignore` które już dodałem w Fazie 1 (`config.py`, `__pycache__`, `.venv`, `responses/`) — lub zachowanie ich.

### Czego **nie** robić w Fazie 2 (zgodnie z duchem "prywatne narzędzie")

- Nie przepisywać na FastAPI/asyncio.
- Nie modernizować frontendu (Bootstrap 4, jQuery — niech zostaną).
- Nie zamieniać `_thread.start_new_thread()` na `threading.Thread` jeśli faktycznie działa.
- Nie wprowadzać type hints / docstringów / `logging` zamiast `print()` jeżeli nie jest to konieczne dla naprawy.

Decyzja co z każdą z tych "nie-rób" rzeczy do podjęcia po zakończeniu Etapów A+B — wtedy będziemy wiedzieli ile faktycznie kodu trzeba dotykać.

---

## 5. Ryzyka i nie-sprawdzone obszary

### Świadomie nie-sprawdzone (poza zakresem Fazy 1)

- **Pełen booking flow** (`getToken`, `saveTerm`, `lockTerm`, `confirmVisit`) — nie wiemy czy działa, czy nie. Możliwe że WSZYSTKO za login jest na nowym JWT API i będzie 500 dopóki nie naprawimy autoryzacji. Skoro `searchVisits` 500, kolejne kroki tym bardziej.
- **Polling pętla w `__main__`** — main.py:502 wywołuje `searchVisits()` bez argumentu (wymagany `exam_id`). Bug istnieje w obecnym kodzie i wywróciłby pętlę przy pierwszym pełnym uruchomieniu. Test scrapper nie odpalał tego kodu, więc bug nigdy się nie ujawnił.
- **Frontend (Flask routes + templates)** — nie testowaliśmy `flaskServer.py`, `index.html` itd. Skoro core scrapping nie działa, frontend mógłby również wymagać aktualizacji (zwłaszcza globalny `storage = {}`).

### Nieznane unknowns

- **Czy Luxmed ma rate limiting / anti-bot który będzie nas dotykał** przy częstym pollowaniu (15-45s intervals)? `getGroupsIds` i login przeszły bez problemu, ale to były pojedyncze requesty.
- **Czy konto wymaga weryfikacji 2FA / SMS code** w niektórych okolicznościach? JWT zawiera `mfadevicestatus: Untrusted` — może być scenariusz gdzie portal wymaga MFA.
- **Czy struktura JSON dla `terms` (po naprawie searcha) jest taka sama jak 5 lat temu?** Zobaczymy dopiero gdy search zwróci 200.

### Ryzyko bezpieczeństwa

- Hasło `config.py` zostało wyświetlone w transkrypcie sesji Claude'a (zaakceptowane przez Adriana, ale **mocna rekomendacja** żeby zmienić po skończeniu prac).
- Sam scrapper sprzed 5 lat — żadnych zależności w `requirements.txt`, niezablokowanych wersji, więc Faza 2 powinna pinować `requests`, `flask` itd. do konkretnych wersji.

---

## Załączniki

| Plik                                                 | Co tam jest                                                |
| ---------------------------------------------------- | ---------------------------------------------------------- |
| `/tmp/luxmed_recon_outputs/01_main_page.html`        | HTML strony loginu Angulara — dla diagnozy struktury       |
| `/tmp/luxmed_recon_outputs/02_after_login.html`      | JSON response z loginu (mimo .html w nazwie) — JWT i flagi |
| `/tmp/luxmed_recon_outputs/03_groups.json`           | Surowa lista usług/lekarzy/klinik z portalu                |
| `/tmp/luxmed_recon_outputs/03_varieties.json`        | Po przejściu przez `LuxmedParser.parseVarieties()`         |
| `/tmp/luxmed_recon_outputs/04_visits_500_error.html` | Generic error page Luxmedu (HTTP 500 z `terms/index`)      |
| `/tmp/luxmed_recon.py`                               | Sam skrypt rekonu (poza repo, nie commitowany)             |

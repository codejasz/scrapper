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

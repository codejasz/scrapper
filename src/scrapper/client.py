"""LuxmedClient — HTTP + JWT. Inne endpointy dochodzą w kolejnych taskach."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import jwt as jwt_lib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import (
    Doctor,
    LockResult,
    OneDayTermsResponse,
    Place,
    ReservationSummary,
    SearchContext,
    Term,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://portalpacjenta.luxmed.pl/PatientPortal"
LOGIN_URL = f"{BASE_URL}/Account/LogIn"
GROUPS_URL = f"{BASE_URL}/NewPortal/Dictionary/serviceVariantsGroups"
ONE_DAY_TERMS_URL = f"{BASE_URL}/NewPortal/terms/oneDayTerms"
SAVE_URL = f"{BASE_URL}/NewPortal/AvailabilityLog/Save"
LOCK_URL = f"{BASE_URL}/NewPortal/Reservation/LockTerm"
UPCOMING_VISITS_URL = f"{BASE_URL}/NewPortal/DashboardMedicalSection/GetUpcomingVisits"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    "Origin": "https://portalpacjenta.luxmed.pl",
    "Referer": "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/Reservation/Results",
    "X-Requested-With": "XMLHttpRequest",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

JWT_EXPIRY_MARGIN_SECONDS = 60


class AuthError(RuntimeError):
    pass


class LuxmedClient:
    def __init__(self, email: str, password: str) -> None:
        import uuid as _uuid
        self.email = email
        self.password = password
        self._token: str | None = None
        self._process_id: str = str(_uuid.uuid4())  # reused across oneDayTerms calls

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
        self._propagate_xsrf()
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
            ("searchDateTo", day.isoformat()),
            ("processId", self._process_id),
            ("searchByMedicalSpecialist", "false"),
            ("expectedTermsNumber", "2"),
            ("delocalized", "false"),
        ]
        url = f"{ONE_DAY_TERMS_URL}?{urlencode(params)}"
        resp = self.session.get(url)
        if resp.status_code == 429:
            logger.warning("oneDayTerms 429 — sleep 30s i retry")
            time.sleep(30)
            resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return _parse_one_day_terms(data)

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
        if not resp.ok:
            logger.error("LockTerm %s response body: %s", resp.status_code, resp.text[:1000])
            logger.debug("LockTerm request body: %s", body)
        resp.raise_for_status()
        data = resp.json()
        errors = data.get("errors") or []
        if errors:
            err_msg = "; ".join(e.get("message") or str(e) for e in errors)
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

    def get_my_reservations(self) -> list[ReservationSummary]:
        self.ensure_authenticated()
        resp = self.session.get(UPCOMING_VISITS_URL)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("GetUpcomingVisits raw: %s", data)
        return _parse_upcoming_visits(data)


def _parse_upcoming_visits(data: Any) -> list[ReservationSummary]:
    """Parsuje GetUpcomingVisits response → list[ReservationSummary].

    Recon (2026-05-07): endpoint zwraca {"events": [...]}.
    Pojedynczy event shape do ustalenia przy pierwszej wizycie — parser defensywny.
    """
    visits: list[Any] = []
    if isinstance(data, list):
        visits = data
    elif isinstance(data, dict):
        for key in ("events", "visits", "upcomingVisits", "data", "value"):
            if isinstance(data.get(key), list):
                visits = data[key]
                break

    if not visits:
        return []

    results = []
    for v in visits:
        try:
            if not isinstance(v, dict):
                continue
            logger.debug("GetUpcomingVisits event: %s", v)
            rid = str(v.get("eventId") or v.get("reservationId") or v.get("id") or "")
            if not rid:
                logger.warning("GetUpcomingVisits: event bez id — %s", v)
                continue
            date_str = (v.get("visitDate") or v.get("dateTimeFrom")
                        or v.get("date") or v.get("startDate") or "")
            dt = datetime.fromisoformat(date_str) if date_str else datetime.min
            doctor = v.get("doctor") or {}
            doctor_name = (
                f"{doctor.get('name', '')} {doctor.get('lastname', '')}".strip()
                or f"{doctor.get('firstName', '')} {doctor.get('lastName', '')}".strip()
                or v.get("doctorName") or ""
            )
            service_name = (v.get("title") or v.get("serviceName")
                            or v.get("serviceVariantName") or v.get("service") or "")
            results.append(ReservationSummary(
                reservation_id=rid,
                date_time_from=dt,
                doctor_name=str(doctor_name),
                service_name=str(service_name),
            ))
        except Exception as exc:
            logger.warning("Pominięto event wizyty: %s — %s", v, exc)
    return results


def _parse_one_day_terms(data: dict[str, Any]) -> OneDayTermsResponse:
    """Real shape: data['termsForDay'] = {day, correlationId, terms[]}.
    Top-level correlationId duplicates the one inside termsForDay.
    """
    correlation_id = data.get("correlationId")
    tfd = data.get("termsForDay") or {}
    raw_terms = tfd.get("terms") or []
    terms = [_parse_term(rt) for rt in raw_terms]
    return OneDayTermsResponse(terms=terms, correlation_id=correlation_id, raw=data)


def _parse_term(raw: dict[str, Any]) -> Term:
    doc = raw.get("doctor") or {}
    # JSON: serviceId per term (NIE serviceVariantId — to jest na poziomie URL/request)
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
        service_variant_id=raw.get("serviceId", 0),
        service_variant_name="",  # real API nie zwraca; bierzemy z catalog/CLI
        is_telemedicine=bool(raw.get("isTelemedicine", False)),
        is_additional=bool(raw.get("isAdditional", False)),
        raw=raw,
    )


def _build_lock_term_body(term: Term, ctx: SearchContext) -> dict[str, Any]:
    """Body LockTerm — explicit shape per recon (curls/lock_term.sh).
    NIE zawiera processId; zawiera correlationId z ostatniego oneDayTerms.
    `date` to ISO UTC midnight (dzień bez godziny), godziny osobno jako stringi.
    """
    raw = term.raw
    day_iso = term.date_time_from.strftime("%Y-%m-%dT00:00:00.000Z")
    return {
        "serviceVariantId": term.service_variant_id,
        "serviceVariantName": term.service_variant_name,
        "facilityId": term.facility_id,
        "facilityName": term.facility_name,
        "roomId": term.room_id,
        "scheduleId": term.schedule_id,
        "date": day_iso,
        "timeFrom": term.date_time_from.strftime("%H:%M"),
        "timeTo": term.date_time_to.strftime("%H:%M"),
        "doctorId": term.doctor.id,
        "doctor": {
            "id": term.doctor.id,
            "academicTitle": term.doctor.academic_title,
            "firstName": term.doctor.first_name,
            "lastName": term.doctor.last_name,
        },
        "isAdditional": term.is_additional,
        "isImpediment": bool(raw.get("isImpediment", False)),
        "impedimentText": raw.get("impedimentText", "") or "",
        "isPreparationRequired": bool(raw.get("isPreparationRequired", False)),
        "preparationItems": raw.get("preparationItems") or [],
        "referralId": raw.get("referralId"),
        "eReferralId": raw.get("eReferralId"),
        "referralTypeId": raw.get("referralTypeId"),
        "parentReservationId": raw.get("parentReservationId"),
        "correlationId": ctx.correlation_id,
        "isTelemedicine": term.is_telemedicine,
        "isPoz": bool(raw.get("isPoz", False)),
        "isRehabilitation": bool(raw.get("isRehabilitation", False)),
        "isOnWhiteList": bool(raw.get("isOnWhiteList", False)),
        "rehabilitationTermContext": raw.get("rehabilitationTermContext"),
        "isVideoConsultation": bool(raw.get("isVideoConsultation", False)),
    }

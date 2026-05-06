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

from .models import Doctor, OneDayTermsResponse, Place, Term

logger = logging.getLogger(__name__)

BASE_URL = "https://portalpacjenta.luxmed.pl/PatientPortal"
LOGIN_URL = f"{BASE_URL}/Account/LogIn"
GROUPS_URL = f"{BASE_URL}/NewPortal/Dictionary/serviceVariantsGroups"
ONE_DAY_TERMS_URL = f"{BASE_URL}/NewPortal/terms/oneDayTerms"

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
            ("searchDatePreset", "14"),
            ("expectedTermsNumber", "1"),
            ("delocalized", "false"),
        ]
        url = f"{ONE_DAY_TERMS_URL}?{urlencode(params)}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return _parse_one_day_terms(data)


def _parse_one_day_terms(data: dict[str, Any]) -> OneDayTermsResponse:
    correlation_id = data.get("correlationId")
    terms: list[Term] = []
    days = ((data.get("termsForService") or {}).get("termsForDays") or [])
    for day_block in days:
        for raw_term in day_block.get("terms") or []:
            terms.append(_parse_term(raw_term))
    return OneDayTermsResponse(terms=terms, correlation_id=correlation_id, raw=data)


def _parse_term(raw: dict[str, Any]) -> Term:
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

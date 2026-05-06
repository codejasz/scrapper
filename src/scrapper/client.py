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

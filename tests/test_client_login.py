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
    assert client._token == jwt2

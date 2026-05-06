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
    client.session.cookies.set("XSRF-TOKEN", "xsrfvalue123")
    groups = client.get_service_groups()

    assert isinstance(groups, list)
    assert groups[0]["name"] == "Konsultacje"

    groups_request = adapter.calls[1]
    assert groups_request.headers.get("XSRF-TOKEN") == "xsrfvalue123"
    assert groups_request.headers.get("Authorization-Token") is not None

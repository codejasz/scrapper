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
    assert body["isPoz"] is False
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

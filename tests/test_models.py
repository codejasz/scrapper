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

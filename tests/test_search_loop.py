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

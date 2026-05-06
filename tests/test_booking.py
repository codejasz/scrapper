from datetime import datetime
from unittest.mock import MagicMock

from scrapper.booking import lock
from scrapper.models import Doctor, LockResult, SearchContext, Term


def _term() -> Term:
    return Term(
        date_time_from=datetime(2026, 5, 8, 17, 0),
        date_time_to=datetime(2026, 5, 8, 17, 30),
        doctor=Doctor(id=1, first_name="J", last_name="K"),
        facility_id=20, facility_name="C", room_id=1, schedule_id=1,
        service_variant_id=4436, service_variant_name="O",
        is_telemedicine=False, is_additional=False, raw={},
    )


def test_lock_calls_save_then_lock_term_in_order():
    client = MagicMock()
    client.lock_term.return_value = LockResult(
        success=True, temporary_reservation_id="r-1", error=None, raw={},
    )
    ctx = SearchContext(process_id="p", correlation_id="c", search_parameters={})

    result = lock(client, _term(), ctx)

    assert result.success is True
    client.save_availability_log.assert_called_once_with(ctx)
    client.lock_term.assert_called_once()
    # Method-call ordering in mock_calls:
    names = [c[0] for c in client.mock_calls]
    assert names.index("save_availability_log") < names.index("lock_term")


def test_lock_returns_failure_when_lockterm_fails():
    client = MagicMock()
    client.lock_term.return_value = LockResult(
        success=False, temporary_reservation_id=None, error="Zajęty", raw={},
    )
    ctx = SearchContext(process_id="p", correlation_id="c", search_parameters={})

    result = lock(client, _term(), ctx)

    assert result.success is False
    assert result.error == "Zajęty"

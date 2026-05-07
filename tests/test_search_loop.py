from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from scrapper.models import Doctor, OneDayTermsResponse, Place, ReservationSummary, Term
from scrapper.search import SearchCriteria, find_matching_term, poll_loop, watch_loop


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
    """Per-day search: dzień 1 pusty, dzień 2 ma matching term."""
    client = MagicMock()
    client.get_one_day_terms.side_effect = [
        OneDayTermsResponse(terms=[], correlation_id="c1", raw={}),
        OneDayTermsResponse(
            terms=[_term(datetime(2026, 5, 6, 17, 0))], correlation_id="c2", raw={},
        ),
    ]

    found = find_matching_term(client, _crit(), between_days_sleep=None)

    assert found is not None
    assert found.date_time_from == datetime(2026, 5, 6, 17, 0)
    assert client.get_one_day_terms.call_count == 2


def test_find_matching_term_returns_none_when_nothing_matches():
    client = MagicMock()
    client.get_one_day_terms.return_value = OneDayTermsResponse(
        terms=[], correlation_id="c", raw={},
    )
    assert find_matching_term(client, _crit(), between_days_sleep=None) is None


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


# ---------- watch_loop ----------


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _reservation(rid: str) -> ReservationSummary:
    return ReservationSummary(
        reservation_id=rid,
        date_time_from=datetime(2026, 5, 10, 10, 0),
        doctor_name="Dr X",
        service_name="Konsultacja",
    )


def _client_with_terms(terms_per_day: list[list[Term]]):
    """Client zwracający kolejne dni cyklicznie — pierwszy sweep zużywa N dni,
    drugi sweep też N. Lista wystarczająco długa = max_iterations * dni_w_zakresie.
    """
    client = MagicMock()
    responses = [OneDayTermsResponse(terms=t, correlation_id="c", raw={})
                 for t in terms_per_day]
    client.get_one_day_terms.side_effect = responses
    return client


def test_watch_loop_alerts_once_for_same_slot():
    """Ten sam slot widziany w dwóch sweepach → tylko jeden alert (dedup)."""
    term = _term(datetime(2026, 5, 6, 17, 0))
    # 2 dni w zakresie × 2 iteracje, slot zawsze w drugim dniu.
    client = _client_with_terms([[], [term], [], [term]])

    alerts: list[Term] = []
    clock = _FakeClock()

    result = watch_loop(
        client, _crit(),
        on_alert=lambda t: alerts.append(t),
        fetch_reservations=lambda: [],
        baseline_reservation_ids=set(),
        cooldown_seconds=300,
        sleep_min=0, sleep_max=0,
        max_iterations=2,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert len(alerts) == 1
    assert result.exit_reason == "max_iterations"
    assert result.iterations == 2


def test_watch_loop_exits_on_new_reservation():
    """Sweep znajduje slot → alert → cooldown active → fetch widzi nowe ID → exit."""
    term = _term(datetime(2026, 5, 6, 17, 0))
    client = _client_with_terms([[term], [term]])  # 2 dni × 1 iteracja

    alerts: list[Term] = []
    clock = _FakeClock()

    fetch_calls = []

    def fetch():
        fetch_calls.append(clock.now())
        return [_reservation("R-NEW-123")]

    result = watch_loop(
        client, _crit(),
        on_alert=lambda t: alerts.append(t),
        fetch_reservations=fetch,
        baseline_reservation_ids={"R-OLD-1"},
        cooldown_seconds=300,
        sleep_min=0, sleep_max=0,
        max_iterations=5,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert len(alerts) == 1
    assert result.exit_reason == "new_reservation"
    assert result.new_reservation is not None
    assert result.new_reservation.reservation_id == "R-NEW-123"
    assert len(fetch_calls) == 1


def test_watch_loop_does_not_fetch_reservations_before_first_alert():
    """Cooldown nie aktywny → fetch_reservations nie wołane."""
    client = _client_with_terms([[], [], [], []])  # 2 dni × 2 iteracje, brak slotów

    fetch_called = []
    clock = _FakeClock()

    watch_loop(
        client, _crit(),
        on_alert=lambda t: None,
        fetch_reservations=lambda: fetch_called.append(1) or [],
        baseline_reservation_ids=set(),
        cooldown_seconds=300,
        sleep_min=0, sleep_max=0,
        max_iterations=2,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert fetch_called == []


def test_watch_loop_continues_when_no_new_reservation():
    """Cooldown active, fetch zwraca tylko baseline → kontynuuj do max_iterations."""
    term = _term(datetime(2026, 5, 6, 17, 0))
    client = _client_with_terms([[term], [term], [term], [term]])  # 2 dni × 2 iter

    alerts: list[Term] = []
    clock = _FakeClock()

    result = watch_loop(
        client, _crit(),
        on_alert=lambda t: alerts.append(t),
        fetch_reservations=lambda: [_reservation("R-OLD-1")],
        baseline_reservation_ids={"R-OLD-1"},
        cooldown_seconds=300,
        sleep_min=0, sleep_max=0,
        max_iterations=2,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert result.exit_reason == "max_iterations"
    assert len(alerts) == 1


def test_watch_loop_swallows_fetch_reservations_exception():
    """fetch_reservations rzuca → log warn, treat jak no new, kontynuuj."""
    term = _term(datetime(2026, 5, 6, 17, 0))
    client = _client_with_terms([[term], [term], [term], [term]])

    clock = _FakeClock()

    def boom():
        raise RuntimeError("network down")

    result = watch_loop(
        client, _crit(),
        on_alert=lambda t: None,
        fetch_reservations=boom,
        baseline_reservation_ids=set(),
        cooldown_seconds=300,
        sleep_min=0, sleep_max=0,
        max_iterations=2,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert result.exit_reason == "max_iterations"


def test_watch_loop_skips_reservation_check_after_cooldown_expires():
    """Po cooldown expired (now >= cooldown_until) — fetch_reservations NIE wołane."""
    term = _term(datetime(2026, 5, 6, 17, 0))
    client = _client_with_terms([[term], [term], [term], [term]])

    clock = _FakeClock()
    fetch_calls = []

    def fetch():
        fetch_calls.append(clock.now())
        return []

    # cooldown=10s; iter1 znajduje slot, ustawia cooldown_until=10.
    # iter1 sprawdza fetch (now=0 < 10). sleep_fn przesunie clock o sleep_max=15
    # → iter2: now=15 ≥ 10, fetch NIE wołany.
    watch_loop(
        client, _crit(),
        on_alert=lambda t: None,
        fetch_reservations=fetch,
        baseline_reservation_ids=set(),
        cooldown_seconds=10,
        sleep_min=15, sleep_max=15,
        max_iterations=2,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )

    assert len(fetch_calls) == 1  # tylko iter1, iter2 po cooldown expired

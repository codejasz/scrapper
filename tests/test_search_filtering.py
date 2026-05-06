from datetime import date, datetime

from scrapper.models import Doctor, Place, Term
from scrapper.search import SearchCriteria, iter_days, matches


def _term(*, dt: datetime, doctor_last: str = "Kowalski",
          facility: str = "Klinika Swobodna") -> Term:
    return Term(
        date_time_from=dt,
        date_time_to=dt,
        doctor=Doctor(id=1, first_name="Jan", last_name=doctor_last),
        facility_id=20,
        facility_name=facility,
        room_id=1, schedule_id=1, service_variant_id=4436,
        service_variant_name="Ortopeda",
        is_telemedicine=False, is_additional=False, raw={},
    )


def _crit(**overrides) -> SearchCriteria:
    base = dict(
        service_id=4436,
        place=Place(id=5, name="Wrocław"),
        date_from=datetime(2026, 5, 5, 16, 0),
        date_to=datetime(2026, 5, 10, 19, 0),
    )
    base.update(overrides)
    return SearchCriteria(**base)


def test_matches_returns_true_when_inside_window():
    term = _term(dt=datetime(2026, 5, 7, 17, 0))
    assert matches(term, _crit()) is True


def test_matches_returns_false_when_before_window():
    term = _term(dt=datetime(2026, 5, 5, 14, 0))
    assert matches(term, _crit()) is False


def test_matches_returns_false_when_after_window():
    term = _term(dt=datetime(2026, 5, 10, 20, 0))
    assert matches(term, _crit()) is False


def test_matches_doctor_filter_case_insensitive():
    term = _term(dt=datetime(2026, 5, 7, 17, 0), doctor_last="KOWALSKI")
    assert matches(term, _crit(doctor_filter="kowal")) is True
    assert matches(term, _crit(doctor_filter="nowak")) is False


def test_matches_facility_filter_case_insensitive():
    term = _term(dt=datetime(2026, 5, 7, 17, 0), facility="Klinika Swobodna")
    assert matches(term, _crit(facility_filter="swobodna")) is True
    assert matches(term, _crit(facility_filter="legnicka")) is False


def test_iter_days_yields_dates_inclusive():
    crit = _crit(
        date_from=datetime(2026, 5, 5, 0, 0),
        date_to=datetime(2026, 5, 7, 23, 59),
    )
    days = list(iter_days(crit))
    assert days == [date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7)]


def test_iter_days_single_day():
    crit = _crit(
        date_from=datetime(2026, 5, 5, 16, 0),
        date_to=datetime(2026, 5, 5, 19, 0),
    )
    assert list(iter_days(crit)) == [date(2026, 5, 5)]

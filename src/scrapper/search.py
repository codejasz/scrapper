"""Kryteria + dopasowanie + pętla pollująca."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .client import LuxmedClient
from .models import Place, ReservationSummary, Term

logger = logging.getLogger(__name__)


@dataclass
class SearchCriteria:
    service_id: int
    place: Place
    date_from: datetime
    date_to: datetime
    doctor_filter: str | None = None
    facility_filter: str | None = None


def matches(term: Term, crit: SearchCriteria) -> bool:
    if term.date_time_from < crit.date_from or term.date_time_from > crit.date_to:
        return False
    if crit.doctor_filter:
        full = f"{term.doctor.first_name} {term.doctor.last_name}".casefold()
        if crit.doctor_filter.casefold() not in full:
            return False
    if crit.facility_filter:
        if crit.facility_filter.casefold() not in term.facility_name.casefold():
            return False
    return True


def iter_days(crit: SearchCriteria) -> Iterator[date]:
    current = crit.date_from.date()
    last = crit.date_to.date()
    while current <= last:
        yield current
        current += timedelta(days=1)


def find_matching_term(
    client: LuxmedClient,
    crit: SearchCriteria,
    *,
    between_days_sleep: tuple[float, float] | None = (1.2, 2.0),
) -> Term | None:
    """Per-day iteracja: oneDayTerms zwraca tylko jeden dzień (searchDateFrom==searchDateTo).
    `between_days_sleep`: jitter między requestami. None wyłącza (testy).
    """
    first = True
    for day in iter_days(crit):
        if not first and between_days_sleep is not None:
            time.sleep(random.uniform(*between_days_sleep))
        first = False
        response = client.get_one_day_terms(
            service_id=crit.service_id, place=crit.place, day=day,
        )
        for term in response.terms:
            if matches(term, crit):
                logger.info("Match: %s %s, %s", term.date_time_from.isoformat(),
                            term.doctor.full_name(), term.facility_name)
                return term
    return None


def poll_loop(
    client: LuxmedClient,
    crit: SearchCriteria,
    *,
    sleep_min: int = 30,
    sleep_max: int = 90,
    max_iterations: int | None = None,
) -> Term:
    iteration = 0
    while True:
        iteration += 1
        logger.info("Sweep #%d: %s → %s", iteration,
                    crit.date_from.isoformat(), crit.date_to.isoformat())
        found = find_matching_term(client, crit)
        if found:
            return found
        if max_iterations is not None and iteration >= max_iterations:
            raise TimeoutError(
                f"Brak slotów po {max_iterations} iteracjach"
            )
        delay = random.randint(sleep_min, sleep_max) if sleep_max > sleep_min else sleep_min
        logger.info("Brak slotów — śpię %ds", delay)
        time.sleep(delay)


@dataclass
class WatchResult:
    exit_reason: str  # "new_reservation" | "max_iterations"
    new_reservation: ReservationSummary | None
    iterations: int


def slot_dedup_key(term: Term) -> tuple[int, str]:
    return term.doctor.id, term.date_time_from.isoformat()


def watch_loop(
    client: LuxmedClient,
    crit: SearchCriteria,
    *,
    on_alert: Callable[[Term], None],
    fetch_reservations: Callable[[], list[ReservationSummary]],
    baseline_reservation_ids: set[str],
    cooldown_seconds: int = 300,
    sleep_min: int = 30,
    sleep_max: int = 90,
    max_iterations: int | None = None,
    now_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> WatchResult:
    """Polling loop z dedup-em, cooldownem i reservation check.

    - find_matching_term per sweep; każdy nowy slot → on_alert + dedup do alerted_keys.
    - Po pierwszym alercie ustaw cooldown_until = now + cooldown_seconds.
    - W trakcie cooldownu: po sweepie sprawdź fetch_reservations() — jeśli
      pojawiło się nowe id (nie w baseline), exit z exit_reason="new_reservation".
    - Reservation fetch failures: log warn i kontynuuj (treat jak "no new").
    """
    alerted_keys: set[tuple[int, str]] = set()
    cooldown_until: float | None = None
    iteration = 0

    while True:
        iteration += 1
        logger.info("Sweep #%d: %s → %s", iteration,
                    crit.date_from.isoformat(), crit.date_to.isoformat())

        found = find_matching_term(client, crit)
        if found:
            key = slot_dedup_key(found)
            if key not in alerted_keys:
                alerted_keys.add(key)
                cooldown_until = now_fn() + cooldown_seconds
                logger.info("Nowy slot — alert + cooldown %ds: %s %s",
                            cooldown_seconds, found.date_time_from.isoformat(),
                            found.doctor.full_name())
                on_alert(found)
            else:
                logger.debug("Slot już zaalertowany — skip: %s", key)

        if cooldown_until is not None and now_fn() < cooldown_until:
            try:
                reservations = fetch_reservations()
            except Exception as exc:  # network, parse, NotImplementedError
                logger.warning("fetch_reservations failed: %s", exc)
                reservations = []
            new = [r for r in reservations if r.reservation_id not in baseline_reservation_ids]
            if new:
                logger.info("Wykryto nową rezerwację — exit: %s",
                            [r.reservation_id for r in new])
                return WatchResult(
                    exit_reason="new_reservation",
                    new_reservation=new[0],
                    iterations=iteration,
                )

        if max_iterations is not None and iteration >= max_iterations:
            return WatchResult(
                exit_reason="max_iterations",
                new_reservation=None,
                iterations=iteration,
            )

        delay = random.randint(sleep_min, sleep_max) if sleep_max > sleep_min else sleep_min
        logger.info("Sweep koniec — śpię %ds", delay)
        sleep_fn(delay)

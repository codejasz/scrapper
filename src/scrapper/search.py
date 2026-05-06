"""Kryteria + dopasowanie + pętla pollująca."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .client import LuxmedClient
from .models import Place, Term

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
    between_days_sleep: tuple[float, float] | None = (0.3, 0.7),
) -> Term | None:
    """`between_days_sleep`: jitter między requestami. None wyłącza (testy)."""
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

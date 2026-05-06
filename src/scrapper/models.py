"""Dataclassy domeny — tyle pól ile potrzebne dla flow search → save → lock."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Place:
    id: int
    name: str
    type: int = 0


@dataclass(frozen=True)
class Doctor:
    id: int
    first_name: str
    last_name: str
    academic_title: str | None = None

    def full_name(self) -> str:
        if self.academic_title:
            return f"{self.academic_title} {self.first_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


@dataclass
class Term:
    """Pojedynczy slot z `oneDayTerms`. `raw` trzymamy żeby przekazać 1:1 do LockTerm."""

    date_time_from: datetime
    date_time_to: datetime
    doctor: Doctor
    facility_id: int  # JSON: clinicId (rename: domain term)
    facility_name: str  # JSON: clinic
    room_id: int
    schedule_id: int
    service_variant_id: int
    service_variant_name: str
    is_telemedicine: bool
    is_additional: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchContext:
    """Stan sesji wyszukiwania potrzebny do Save/LockTerm."""

    process_id: str
    correlation_id: str | None
    search_parameters: dict[str, Any]


@dataclass
class OneDayTermsResponse:
    terms: list[Term]
    correlation_id: str | None
    raw: dict[str, Any]


@dataclass
class LockResult:
    success: bool
    temporary_reservation_id: str | None
    error: str | None
    raw: dict[str, Any]

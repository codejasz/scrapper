import time
from datetime import date

import jwt as jwt_lib

from scrapper.client import LuxmedClient
from scrapper.models import Place

from .test_client_login import _MockAdapter


def _jwt() -> str:
    return jwt_lib.encode({"exp": int(time.time()) + 600}, "s", algorithm="HS256")


_SAMPLE_TERMS_RESPONSE = {
    "correlationId": "corr-abc",
    "serviceVariantId": 4436,
    "termsForDay": {
        "day": "2026-05-08T00:00:00",
        "correlationId": "corr-abc",
        "terms": [
            {
                "dateTimeFrom": "2026-05-08T17:00:00",
                "dateTimeTo": "2026-05-08T17:30:00",
                "doctor": {
                    "id": 11, "firstName": "Jan", "lastName": "Kowalski",
                    "academicTitle": "dr", "genderId": 1,
                },
                "clinicId": 20,
                "clinic": "Klinika Swobodna",
                "roomId": 30,
                "scheduleId": 40,
                "serviceId": 4436,
                "isTelemedicine": False,
                "isAdditional": False,
                "preparationItems": [{"id": 99}],
            }
        ],
    },
}


def test_get_one_day_terms_parses_terms_and_correlation_id():
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"}, _SAMPLE_TERMS_RESPONSE),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(service_id=4436, place=place, day=date(2026, 5, 8))

    assert response.correlation_id == "corr-abc"
    assert len(response.terms) == 1
    term = response.terms[0]
    assert term.doctor.first_name == "Jan"
    assert term.facility_name == "Klinika Swobodna"
    assert term.service_variant_id == 4436
    assert term.raw["preparationItems"] == [{"id": 99}]

    request = adapter.calls[1]
    assert "/NewPortal/terms/oneDayTerms" in request.url
    assert "searchPlace.id=5" in request.url
    assert "searchPlace.type=0" in request.url
    assert "serviceVariantId=4436" in request.url
    assert "searchDateFrom=2026-05-08" in request.url
    assert "searchDateTo=2026-05-08" in request.url
    assert "searchByMedicalSpecialist=false" in request.url
    assert "expectedTermsNumber=2" in request.url
    assert "processId=" in request.url


def test_get_one_day_terms_empty_day_returns_no_terms():
    empty_response = {
        "correlationId": "corr-xyz",
        "termsForDay": {"day": "2026-05-08T00:00:00", "correlationId": "corr-xyz", "terms": []},
    }
    adapter = _MockAdapter([
        (200, {"Content-Type": "application/json",
               "Set-Cookie": "XSRF-TOKEN=tk; Path=/"},
         {"succeded": True, "errorMessage": None, "token": _jwt()}),
        (200, {"Content-Type": "application/json"}, empty_response),
    ])
    client = LuxmedClient("a@b.pl", "x")
    client.session.mount("https://", adapter)
    client.login()

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(service_id=4436, place=place, day=date(2026, 5, 8))

    assert response.terms == []
    assert response.correlation_id == "corr-xyz"

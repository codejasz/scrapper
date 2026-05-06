import pytest

from scrapper.catalog import (
    ServiceMatch,
    find_service_by_id,
    find_services_by_name,
)


@pytest.fixture
def groups_fixture() -> list[dict]:
    """Skrócony kształt `serviceVariantsGroups` z prawdziwego endpointu."""
    return [
        {
            "id": 1,
            "name": "Konsultacje",
            "children": [
                {
                    "id": 100,
                    "name": "Ortopedia",
                    "children": [
                        {"id": 4436, "name": "Konsultacja ortopedyczna", "children": []},
                        {"id": 4437, "name": "Ortopeda dziecięcy", "children": []},
                    ],
                },
                {
                    "id": 101,
                    "name": "Inne",
                    "children": [
                        {"id": 9999, "name": "Coś innego", "children": []},
                    ],
                },
            ],
        }
    ]


def test_find_service_by_id_returns_match(groups_fixture):
    match = find_service_by_id(groups_fixture, 4436)
    assert isinstance(match, ServiceMatch)
    assert match.service_id == 4436
    assert match.name == "Konsultacja ortopedyczna"
    assert match.path == ["Konsultacje", "Ortopedia", "Konsultacja ortopedyczna"]


def test_find_service_by_id_missing_returns_none(groups_fixture):
    assert find_service_by_id(groups_fixture, 1) is None


def test_find_services_by_name_substring_case_insensitive(groups_fixture):
    matches = find_services_by_name(groups_fixture, "ortop")
    ids = sorted(m.service_id for m in matches)
    assert ids == [4436, 4437]


def test_find_services_by_name_no_match(groups_fixture):
    assert find_services_by_name(groups_fixture, "kardio") == []


def test_find_services_by_name_empty_query_returns_empty(groups_fixture):
    assert find_services_by_name(groups_fixture, "") == []

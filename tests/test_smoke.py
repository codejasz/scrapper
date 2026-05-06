"""End-to-end smoke. Wymaga .env z LUXMED_EMAIL/LUXMED_PASSWORD.
Uruchom: pytest tests/test_smoke.py -v -s -m smoke
albo: scrapper smoke
"""

from datetime import date

import pytest

from scrapper.client import LuxmedClient
from scrapper.config import load_settings
from scrapper.models import Place


@pytest.mark.smoke
def test_smoke_login_groups_search(env_loaded):
    settings = load_settings(load_dotenv_file=False)
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)

    client.login()
    assert client.is_authenticated()

    groups = client.get_service_groups()
    assert isinstance(groups, list)
    assert len(groups) > 0

    def _first_leaf(nodes):
        for n in nodes:
            children = n.get("children") or []
            if not children and n.get("id"):
                return n["id"]
            found = _first_leaf(children)
            if found:
                return found
        return None

    service_id = _first_leaf(groups)
    assert service_id is not None

    response = client.get_one_day_terms(
        service_id=service_id,
        place=Place(id=5, name="Wrocław"),
        day=date.today(),
    )
    assert response is not None

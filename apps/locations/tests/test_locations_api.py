import pytest

from apps.locations.models import City, Province

pytestmark = pytest.mark.django_db


def test_all_31_provinces_seeded_and_public(api_client):
    r = api_client.get("/api/v1/locations/provinces/")
    assert r.status_code == 200 and len(r.json()) == 31
    names = {p["name"] for p in r.json()}
    assert {"تهران", "فارس", "یزد"} <= names


def test_cities_filter_by_province(api_client):
    fars = Province.objects.get(name="فارس")
    r = api_client.get("/api/v1/locations/cities/", {"province": fars.pk})
    assert r.status_code == 200
    assert "شیراز" in {c["name"] for c in r.json()}
    assert all(c["province"] == fars.pk for c in r.json())
    assert City.objects.filter(province=fars, name="شیراز").exists()


def test_bad_province_param_is_ignored_safely(api_client):
    assert api_client.get("/api/v1/locations/cities/", {"province": "abc"}).status_code == 200

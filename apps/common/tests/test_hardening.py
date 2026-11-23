import importlib
import json

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


# ------------------------------------------------------------------ one error shape everywhere
def test_unknown_api_urls_return_the_json_error_shape(api_client):
    r = api_client.get("/api/v1/does-not-exist/")
    assert r.status_code == 404 and r["Content-Type"].startswith("application/json")
    assert r.json() == {"error": {"code": "not_found", "message": "Not found.", "details": {}}}


def test_non_api_urls_keep_the_normal_html_404(api_client):
    r = api_client.get("/nothing-here/")
    assert r.status_code == 404 and "json" not in r["Content-Type"]


def test_unexpected_errors_return_json_without_leaking_details(monkeypatch):
    from apps.common.views import HealthView

    def boom(self, request):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(HealthView, "get", boom)
    client = APIClient(raise_request_exception=False)
    r = client.get("/api/v1/health/")
    assert r.status_code == 500 and r.json()["error"]["code"] == "server_error"
    assert "hunter2" not in r.content.decode() and "RuntimeError" not in r.content.decode()


def test_wrong_method_and_bad_json_use_the_same_shape(api_client):
    r = api_client.delete("/api/v1/health/")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
    bad = api_client.post("/api/v1/auth/login/", data="{not json", content_type="application/json")
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "parse_error"


# ------------------------------------------------------------------ global rate limits
def test_anonymous_clients_are_rate_limited_everywhere(api_client, monkeypatch):
    monkeypatch.setitem(AnonRateThrottle.THROTTLE_RATES, "anon", "3/min")
    codes = [api_client.get("/api/v1/jobs/").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    body = api_client.get("/api/v1/categories/").json()
    assert body["error"]["code"] == "throttled"


def test_logged_in_users_have_their_own_limit(make_user, auth_client, monkeypatch):
    monkeypatch.setitem(UserRateThrottle.THROTTLE_RATES, "user", "2/min")
    client = auth_client(make_user())
    codes = [client.get("/api/v1/accounts/me/").status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]


def test_x_forwarded_for_cannot_be_used_to_dodge_the_limit(api_client, monkeypatch, settings):
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0  # default: only the socket address counts
    monkeypatch.setitem(AnonRateThrottle.THROTTLE_RATES, "anon", "2/min")
    codes = [
        api_client.get("/api/v1/jobs/", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code
        for i in range(4)
    ]
    assert codes == [200, 200, 429, 429]


def test_health_probe_is_never_throttled(api_client, monkeypatch):
    monkeypatch.setitem(AnonRateThrottle.THROTTLE_RATES, "anon", "1/min")
    assert [api_client.get("/api/v1/health/").status_code for _ in range(5)] == [200] * 5


# ------------------------------------------------------------------ request size
def test_oversized_json_is_refused_before_parsing(api_client):
    big = json.dumps({"email": "a@example.com", "password": "x" * 1_100_000})
    r = api_client.post("/api/v1/auth/register/", data=big, content_type="application/json")
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_normal_sized_requests_are_untouched(api_client):
    r = api_client.post(
        "/api/v1/auth/login/", {"email": "a@example.com", "password": "x"}, format="json"
    )
    assert r.status_code == 401


def test_large_multipart_photo_is_allowed_up_to_its_own_limit(make_seeker, make_user, auth_client):
    client = auth_client(make_seeker())
    from django.core.files.uploadedfile import SimpleUploadedFile

    too_big = SimpleUploadedFile("a.png", b"0" * 3_200_000, "image/png")
    assert (
        client.put("/api/v1/resumes/me/photo/", {"photo": too_big}, format="multipart").status_code
        == 413
    )


# ------------------------------------------------------------------ configuration
@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("DJANGO_ENABLE_API_DOCS", raising=False)
    return monkeypatch


def load_prod():
    return importlib.reload(importlib.import_module("config.settings.prod"))


def test_api_docs_are_off_by_default_in_production(prod_env):
    prod = load_prod()
    assert prod.ENABLE_API_DOCS is False and prod.DEBUG is False
    prod_env.setenv("DJANGO_ENABLE_API_DOCS", "True")
    assert load_prod().ENABLE_API_DOCS is True


def test_production_security_settings(prod_env):
    prod = load_prod()
    assert (
        prod.SESSION_COOKIE_SECURE
        and prod.CSRF_COOKIE_SECURE
        and prod.SECURE_HSTS_SECONDS >= 31536000
    )
    assert prod.SECURE_SSL_REDIRECT is True and prod.SECURE_REFERRER_POLICY == "same-origin"
    assert prod.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")


def test_production_refuses_to_start_without_a_shared_cache(monkeypatch):
    """Per-process counters would make rate limits several times weaker with several workers."""
    from django.core.exceptions import ImproperlyConfigured

    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ImproperlyConfigured, match="REDIS_URL"):
        load_prod()


def test_no_default_secret_in_settings(settings):
    assert settings.SECRET_KEY and "change-me" not in settings.SECRET_KEY
    base = open("config/settings/base.py").read()
    assert 'env("DJANGO_SECRET_KEY")' in base  # no fallback value: missing key stops startup

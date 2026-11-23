import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from conftest import PASSWORD

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/token/refresh/"
LOGOUT = "/api/v1/auth/logout/"


def login(client, email, password=PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


# ---------- registration ----------
def test_register_success_hides_password(api_client):
    r = api_client.post(REGISTER, {"email": "New@Example.com", "password": PASSWORD}, format="json")
    assert r.status_code == 201
    assert r.json()["email"] == "new@example.com"
    assert "password" not in r.json()


def test_register_duplicate_email_case_insensitive(api_client, make_user):
    make_user("taken@example.com")
    r = api_client.post(
        REGISTER, {"email": "TAKEN@example.com", "password": PASSWORD}, format="json"
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"
    assert "email" in r.json()["error"]["details"]


@pytest.mark.parametrize("weak", ["12345678", "short", "password"])
def test_register_rejects_weak_password(api_client, weak):
    r = api_client.post(REGISTER, {"email": "w@example.com", "password": weak}, format="json")
    assert r.status_code == 400
    assert "password" in r.json()["error"]["details"]


def test_register_rejects_bad_phone_and_duplicate_phone(api_client, make_user):
    make_user(phone="09123456789")
    bad = api_client.post(
        REGISTER, {"email": "a@example.com", "password": PASSWORD, "phone": "123"}, format="json"
    )
    dup = api_client.post(
        REGISTER,
        {"email": "b@example.com", "password": PASSWORD, "phone": "09123456789"},
        format="json",
    )
    assert bad.status_code == 400 and dup.status_code == 400


def test_register_cannot_set_staff_flags(api_client):
    r = api_client.post(
        REGISTER,
        {"email": "evil@example.com", "password": PASSWORD, "is_staff": True, "is_superuser": True},
        format="json",
    )
    assert r.status_code == 201
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.get(email="evil@example.com")
    assert not user.is_staff and not user.is_superuser


# ---------- login / refresh / logout ----------
def test_login_success_returns_tokens(api_client, make_user):
    make_user("a@example.com")
    r = login(api_client, "A@Example.com")  # case-insensitive
    assert r.status_code == 200
    assert set(r.json()) == {"access", "refresh"}


def test_login_wrong_password_is_401_with_envelope(api_client, make_user):
    make_user("a@example.com")
    r = login(api_client, "a@example.com", "wrong-password-1")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "authentication_failed"


def test_login_inactive_user_rejected(api_client, make_user):
    make_user("a@example.com", is_active=False)
    assert login(api_client, "a@example.com").status_code == 401


def test_refresh_rotates_and_old_token_is_blacklisted(api_client, make_user):
    make_user("a@example.com")
    old = login(api_client, "a@example.com").json()["refresh"]
    first = api_client.post(REFRESH, {"refresh": old}, format="json")
    assert first.status_code == 200 and first.json()["refresh"] != old
    reuse = api_client.post(REFRESH, {"refresh": old}, format="json")
    assert reuse.status_code == 401


def test_logout_blacklists_refresh_token(api_client, make_user):
    make_user("a@example.com")
    refresh = login(api_client, "a@example.com").json()["refresh"]
    assert api_client.post(LOGOUT, {"refresh": refresh}, format="json").status_code == 204
    assert api_client.post(REFRESH, {"refresh": refresh}, format="json").status_code == 401


def test_logout_with_garbage_token_is_400(api_client):
    r = api_client.post(LOGOUT, {"refresh": "not-a-token"}, format="json")
    assert r.status_code == 400


def test_protected_endpoint_requires_token(api_client):
    r = api_client.get("/api/v1/accounts/me/")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_access_token_works_on_protected_endpoint(make_user):
    make_user("a@example.com")
    client = APIClient()
    access = login(client, "a@example.com").json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r = client.get("/api/v1/accounts/me/")
    assert r.status_code == 200 and r.json()["email"] == "a@example.com"


# ---------- password change ----------
def test_password_change_flow(make_user, auth_client):
    user = make_user("a@example.com")
    anon = APIClient()
    refresh = login(anon, "a@example.com").json()["refresh"]
    client = auth_client(user)

    bad = client.post(
        "/api/v1/auth/password/change/",
        {"old_password": "nope", "new_password": "An0ther-pass-456"},
        format="json",
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/auth/password/change/",
        {"old_password": PASSWORD, "new_password": "An0ther-pass-456"},
        format="json",
    )
    assert ok.status_code == 204
    assert anon.post(REFRESH, {"refresh": refresh}, format="json").status_code == 401
    assert login(anon, "a@example.com", "An0ther-pass-456").status_code == 200
    assert login(anon, "a@example.com", PASSWORD).status_code == 401


def test_password_change_requires_auth(api_client):
    r = api_client.post(
        "/api/v1/auth/password/change/", {"old_password": "x", "new_password": "y"}, format="json"
    )
    assert r.status_code == 401


# ---------- password reset ----------
def _extract(link_mail):
    body = link_mail.body
    return (
        re.search(r"uid=([^&\s]+)", body).group(1),
        re.search(r"token=([^&\s]+)", body).group(1),
    )


def test_password_reset_unknown_email_gives_same_answer_and_sends_nothing(api_client):
    r = api_client.post(
        "/api/v1/auth/password/reset/", {"email": "ghost@example.com"}, format="json"
    )
    assert r.status_code == 200
    assert mail.outbox == []


def test_password_reset_full_flow_and_single_use(api_client, make_user):
    make_user("a@example.com")
    r = api_client.post("/api/v1/auth/password/reset/", {"email": "A@example.com"}, format="json")
    assert r.status_code == 200 and len(mail.outbox) == 1
    uid, token = _extract(mail.outbox[0])

    confirm = "/api/v1/auth/password/reset/confirm/"
    payload = {"uid": uid, "token": token, "new_password": "Brand-new-pass-789"}
    assert api_client.post(confirm, payload, format="json").status_code == 204
    assert login(api_client, "a@example.com", "Brand-new-pass-789").status_code == 200
    assert api_client.post(confirm, payload, format="json").status_code == 400  # token used


def test_password_reset_rejects_bad_token_and_weak_password(api_client, make_user):
    user = make_user("a@example.com")
    from apps.accounts.services import make_reset_credentials

    uid, token = make_reset_credentials(user)
    confirm = "/api/v1/auth/password/reset/confirm/"
    bad = api_client.post(
        confirm,
        {"uid": uid, "token": "bad-token", "new_password": "Brand-new-pass-789"},
        format="json",
    )
    weak = api_client.post(
        confirm, {"uid": uid, "token": token, "new_password": "12345678"}, format="json"
    )
    assert bad.status_code == 400 and weak.status_code == 400


def test_password_reset_not_sent_to_inactive_user(api_client, make_user):
    make_user("a@example.com", is_active=False)
    api_client.post("/api/v1/auth/password/reset/", {"email": "a@example.com"}, format="json")
    assert mail.outbox == []


# ---------- me / deactivate ----------
def test_me_returns_roles_and_hides_sensitive_fields(make_seeker, auth_client):
    user = make_seeker()
    data = auth_client(user).get("/api/v1/accounts/me/").json()
    assert data["roles"] == {"is_job_seeker": True, "is_employer": False, "is_admin": False}
    assert "password" not in data and "is_staff" not in data


def test_me_patch_cannot_change_email_or_staff_flags(make_user, auth_client):
    user = make_user("a@example.com")
    r = auth_client(user).patch(
        "/api/v1/accounts/me/",
        {"email": "hacked@example.com", "is_staff": True, "phone": "09120000000"},
        format="json",
    )
    user.refresh_from_db()
    assert r.status_code == 200
    assert user.email == "a@example.com" and not user.is_staff
    assert user.phone == "09120000000"


def test_me_phone_must_be_unique(make_user, auth_client):
    make_user(phone="09121111111")
    other = make_user()
    r = auth_client(other).patch("/api/v1/accounts/me/", {"phone": "09121111111"}, format="json")
    assert r.status_code == 400


def test_deactivate_requires_password_then_blocks_login_and_refresh(make_user, auth_client):
    user = make_user("a@example.com")
    anon = APIClient()
    refresh = login(anon, "a@example.com").json()["refresh"]
    client = auth_client(user)
    url = "/api/v1/accounts/me/deactivate/"

    assert client.post(url, {"password": "wrong"}, format="json").status_code == 400
    assert client.post(url, {"password": PASSWORD}, format="json").status_code == 204
    assert login(anon, "a@example.com").status_code == 401
    assert anon.post(REFRESH, {"refresh": refresh}, format="json").status_code == 401


def test_login_is_rate_limited(api_client, make_user, monkeypatch):
    from django.core.cache import cache
    from rest_framework.throttling import ScopedRateThrottle

    cache.clear()
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "auth_login", "3/min")
    make_user("a@example.com")
    codes = [login(api_client, "a@example.com", "wrong-password-1").status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]
    cache.clear()


def test_smtp_is_configurable_from_the_environment(settings):
    for name in (
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
        "EMAIL_TIMEOUT",
    ):
        assert hasattr(settings, name), (
            name
        )  # production needs a real SMTP server to send reset links


def test_reset_email_task_is_retried_when_the_mail_server_is_down():
    from apps.accounts.tasks import send_password_reset_email

    assert OSError in send_password_reset_email.autoretry_for
    assert send_password_reset_email.max_retries == 3

"""Guards the whole API surface, not single endpoints.

Every route is discovered automatically. A new endpoint that forgets its permission class fails
here instead of silently becoming public."""

import re

import pytest
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

# The ONLY endpoints reachable without logging in. Anything else must answer 401.
PUBLIC = {
    ("health", "GET"),
    ("auth-register", "POST"),
    ("auth-login", "POST"),
    ("auth-refresh", "POST"),
    ("auth-logout", "POST"),
    ("auth-password-reset", "POST"),
    ("auth-password-reset-confirm", "POST"),
    ("job-list", "GET"),
    ("job-employment", "GET"),
    ("job-projects", "GET"),
    ("job-detail", "GET"),
    ("category-list", "GET"),
    ("province-list", "GET"),
    ("city-list", "GET"),
    ("schema", "GET"),
    ("swagger-ui", "GET"),
}

# Reachable by ANY logged-in user (no profile needed). Everything else must refuse a plain
# account that has no job seeker profile, no employer profile and no staff flag (403 or 404).
ANY_LOGGED_IN = {
    ("account-me", "GET"),
    ("account-me", "PATCH"),
    ("account-deactivate", "POST"),
    ("account-erase", "POST"),
    ("auth-password-change", "POST"),
    ("matching-status", "GET"),
    ("skill-list", "GET"),
    ("job-title-list", "GET"),
    ("skill-suggestions", "GET"),
    ("skill-suggestions", "POST"),
    ("job-title-suggestions", "GET"),
    ("job-title-suggestions", "POST"),
    ("profile-job-seeker", "GET"),
    ("profile-job-seeker", "POST"),
    ("profile-job-seeker", "PATCH"),
    ("profile-employer", "GET"),
    ("profile-employer", "POST"),
    ("profile-employer", "PATCH"),
    ("job-detail", "GET"),
}
SKIP_METHODS = {"options", "head", "trace"}


def iter_routes(patterns=None, prefix=""):
    for p in patterns or get_resolver().url_patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from iter_routes(p.url_patterns, route)
        else:
            yield p.name, route, p.callback


def api_routes():
    routes = []
    for name, route, callback in iter_routes():
        if route.startswith("admin/") or getattr(callback, "__module__", "").startswith("django."):
            continue  # Django's own admin site has its own login
        cls = getattr(callback, "cls", None)
        if cls is None:
            continue
        actions = getattr(callback, "actions", None)
        methods = (
            {m.upper() for m in actions}
            if actions
            else {
                m.upper()
                for m in cls.http_method_names
                if m not in SKIP_METHODS and hasattr(cls, m)
            }
        )
        path = re.sub(r"\(\?P<\w+>[^)]+\)", "1", route)  # router regex groups
        path = "/" + re.sub(r"<(?:\w+:)?\w+>", "1", path.replace("^", "").replace("$", ""))
        routes += [(name, method, path) for method in sorted(methods)]
    return routes


ROUTES = api_routes()


def call(client, method, path):
    return client.generic(method, path, data="{}", content_type="application/json")


def test_the_matrix_actually_covers_the_api():
    names = {name for name, _, _ in ROUTES}
    assert len(ROUTES) > 100  # sanity: discovery works
    assert {
        "job-detail",
        "application-transition",
        "matching-candidates",
        "admin-job-approve",
    } <= names
    assert PUBLIC <= {(n, m) for n, m, _ in ROUTES}  # every allow-listed route still exists


@pytest.mark.parametrize(("name", "method", "path"), ROUTES, ids=lambda v: str(v))
def test_anonymous_users_only_reach_the_public_allow_list(name, method, path):
    response = call(APIClient(), method, path)
    assert response.status_code < 500, f"{method} {path} crashed"
    if (name, method) not in PUBLIC:
        assert response.status_code == 401, f"{method} {path} ({name}) is reachable without login"


@pytest.mark.parametrize(("name", "method", "path"), ROUTES, ids=lambda v: str(v))
def test_a_plain_account_is_refused_everywhere_role_based(
    name, method, path, make_user, auth_client
):
    if (name, method) in PUBLIC or (name, method) in ANY_LOGGED_IN:
        pytest.skip("open by design")
    response = call(auth_client(make_user()), method, path)
    assert response.status_code in (403, 404), (
        f"{method} {path} ({name}) answered {response.status_code} to an account with no role"
    )


@pytest.mark.parametrize(
    ("name", "method", "path"), [r for r in ROUTES if "admin-" in str(r[0])], ids=lambda v: str(v)
)
def test_staff_endpoints_refuse_even_employers_and_job_seekers(
    name, method, path, make_employer, make_seeker, auth_client
):
    for user in (make_employer(), make_seeker()):
        assert call(auth_client(user), method, path).status_code == 403


def test_every_route_name_is_unique_per_method_so_the_allow_lists_are_unambiguous():
    seen = [(n, m) for n, m, _ in ROUTES if n]
    assert len(seen) == len(set(seen))

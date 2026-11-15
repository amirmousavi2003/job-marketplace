import itertools

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

PASSWORD = "S3cure-pass-123"
_counter = itertools.count(1)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email=None, password=PASSWORD, **extra):
        email = email or f"user{next(_counter)}@example.com"
        return get_user_model().objects.create_user(email, password, **extra)

    return _make


@pytest.fixture
def auth_client():
    """Return an APIClient authenticated as the given user (bypasses JWT)."""

    def _auth(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _auth


@pytest.fixture
def make_employer(make_user):
    from apps.profiles.models import EmployerProfile

    def _make(display_name="Employer", **user_extra):
        user = make_user(**user_extra)
        EmployerProfile.objects.create(user=user, display_name=display_name)
        return user

    return _make


@pytest.fixture
def make_seeker(make_user):
    from apps.profiles.models import JobSeekerProfile

    def _make(first_name="Sara", last_name="Ahmadi", **user_extra):
        user = make_user(**user_extra)
        JobSeekerProfile.objects.create(user=user, first_name=first_name, last_name=last_name)
        return user

    return _make

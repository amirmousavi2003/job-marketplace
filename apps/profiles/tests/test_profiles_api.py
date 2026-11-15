import pytest
from django.db import IntegrityError, transaction

from apps.profiles.models import EmployerProfile, JobSeekerProfile

pytestmark = pytest.mark.django_db

SEEKER = "/api/v1/profiles/job-seeker/me/"
EMPLOYER = "/api/v1/profiles/employer/me/"


def test_profile_endpoints_require_auth(api_client):
    assert api_client.get(SEEKER).status_code == 401
    assert api_client.post(EMPLOYER, {}, format="json").status_code == 401


def test_get_before_create_is_404(make_user, auth_client):
    assert auth_client(make_user()).get(SEEKER).status_code == 404


def test_create_job_seeker_profile(make_user, auth_client):
    user = make_user()
    r = auth_client(user).post(SEEKER, {"first_name": "Sara", "last_name": "Ahmadi"}, format="json")
    assert r.status_code == 201
    assert JobSeekerProfile.objects.get(user=user).first_name == "Sara"


def test_second_create_is_409(make_seeker, auth_client):
    user = make_seeker()
    r = auth_client(user).post(SEEKER, {"first_name": "X", "last_name": "Y"}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_create_validates_required_fields(make_user, auth_client):
    r = auth_client(make_user()).post(SEEKER, {"first_name": ""}, format="json")
    assert r.status_code == 400


def test_one_account_can_be_both_seeker_and_employer(make_user, auth_client):
    user = make_user()
    client = auth_client(user)
    assert (
        client.post(SEEKER, {"first_name": "A", "last_name": "B"}, format="json").status_code == 201
    )
    assert client.post(EMPLOYER, {"display_name": "Shop"}, format="json").status_code == 201
    roles = client.get("/api/v1/accounts/me/").json()["roles"]
    assert roles["is_job_seeker"] and roles["is_employer"]


def test_patch_own_profile_only(make_seeker, auth_client):
    a, b = make_seeker(first_name="A"), make_seeker(first_name="B")
    r = auth_client(a).patch(SEEKER, {"first_name": "Changed"}, format="json")
    assert r.status_code == 200
    assert JobSeekerProfile.objects.get(user=a).first_name == "Changed"
    assert JobSeekerProfile.objects.get(user=b).first_name == "B"


def test_cannot_hijack_profile_by_sending_user_id(make_user, make_seeker, auth_client):
    victim = make_seeker()
    attacker = make_user()
    r = auth_client(attacker).post(
        SEEKER, {"first_name": "A", "last_name": "B", "user": victim.pk}, format="json"
    )
    assert r.status_code == 201
    assert JobSeekerProfile.objects.get(user=attacker).pk != victim.job_seeker_profile.pk
    assert JobSeekerProfile.objects.filter(user=victim).count() == 1


def test_db_enforces_one_profile_per_user(make_user):
    user = make_user()
    EmployerProfile.objects.create(user=user, display_name="One")
    with pytest.raises(IntegrityError), transaction.atomic():
        EmployerProfile.objects.create(user=user, display_name="Two")


def test_deleting_user_removes_profiles(make_seeker):
    user = make_seeker()
    user.delete()
    assert JobSeekerProfile.objects.count() == 0

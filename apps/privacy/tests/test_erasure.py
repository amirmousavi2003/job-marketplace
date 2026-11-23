import io
import os

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.applications.models import (
    Application,
    ApplicationStatusHistory,
    ProjectProposal,
    ProjectProposalStatusHistory,
)
from apps.companies.models import Company, CompanyMembership
from apps.companies.services import create_company
from apps.jobs.models import JobPost
from apps.matching.models import AIMatch
from apps.resumes.models import Education, Resume
from apps.skills.models import SkillSuggestion
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

ERASE = "/api/v1/accounts/me/erase/"
User = get_user_model()


@pytest.fixture(autouse=True)
def tmp_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def erase(client, password=PASSWORD, confirm=True):
    return client.post(ERASE, {"password": password, "confirm": confirm}, format="json")


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (10, 20, 30)).save(buffer, format="PNG")
    return SimpleUploadedFile("p.png", buffer.getvalue(), "image/png")


# ------------------------------------------------------------------ safety rails
def test_needs_login_password_and_explicit_confirmation(api_client, make_user, auth_client):
    assert api_client.post(ERASE, {}, format="json").status_code == 401
    client = auth_client(make_user())
    assert erase(client, password="wrong").status_code == 400
    assert erase(client, confirm=False).status_code == 400
    assert client.post(ERASE, {"password": PASSWORD}, format="json").status_code == 400
    assert User.objects.filter(is_active=True).count() == 1  # nothing happened


def test_staff_accounts_cannot_be_erased(make_user, auth_client):
    admin = make_user(is_staff=True)
    assert erase(auth_client(admin)).status_code == 409
    admin.refresh_from_db()
    assert admin.is_active and admin.is_staff


# ------------------------------------------------------------------ the account itself
def test_account_is_anonymized_and_can_never_log_in(make_user, auth_client):
    user = make_user("real@example.com", phone="09121234567")
    anon = APIClient()
    refresh = anon.post(
        "/api/v1/auth/login/", {"email": "real@example.com", "password": PASSWORD}, format="json"
    ).json()["refresh"]
    assert erase(auth_client(user)).status_code == 204
    user.refresh_from_db()
    assert user.email == f"erased-{user.pk}@erased.invalid" and user.phone is None
    assert not user.is_active and not user.has_usable_password()
    assert authenticate(email="real@example.com", password=PASSWORD) is None
    assert (
        anon.post(
            "/api/v1/auth/login/",
            {"email": "real@example.com", "password": PASSWORD},
            format="json",
        ).status_code
        == 401
    )
    assert (
        anon.post("/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json").status_code
        == 401
    )
    assert "real@example.com" not in str(User.objects.values_list("email", "phone"))


def test_the_email_can_be_used_to_register_again(make_user, auth_client, api_client):
    user = make_user("again@example.com", phone="09120000009")
    erase(auth_client(user))
    r = api_client.post(
        "/api/v1/auth/register/",
        {"email": "again@example.com", "password": PASSWORD, "phone": "09120000009"},
        format="json",
    )
    assert r.status_code == 201


def test_erasing_twice_is_impossible(make_user, auth_client):
    user = make_user()
    client = auth_client(user)
    assert erase(client).status_code == 204
    user.refresh_from_db()
    assert not user.has_usable_password()
    assert erase(auth_client(user)).status_code == 400  # unusable password can no longer confirm


# ------------------------------------------------------------------ job seeker data
def test_resume_photo_and_all_sections_are_deleted(make_applicant, auth_client, tmp_media):
    user = make_applicant(first_name="سارا", last_name="احمدی")
    client = auth_client(user)
    assert (
        client.put("/api/v1/resumes/me/photo/", {"photo": png()}, format="multipart").status_code
        == 200
    )
    photo_path = Resume.objects.get(job_seeker=user.job_seeker_profile).photo.path
    assert os.path.exists(photo_path) and Education.objects.exists()
    assert erase(client).status_code == 204
    assert not os.path.exists(photo_path)
    assert Resume.objects.count() == 0 and Education.objects.count() == 0
    profile = user.job_seeker_profile
    profile.refresh_from_db()
    assert (profile.first_name, profile.last_name) == ("کاربر", "حذف‌شده")


def test_ai_matches_of_the_person_are_deleted(make_applicant, job, auth_client):
    user = make_applicant()
    auth_client(user).get("/api/v1/matching/recommendations/")
    assert AIMatch.objects.count() == 1
    erase(auth_client(user))
    assert AIMatch.objects.count() == 0


def test_applications_are_scrubbed_withdrawn_and_still_visible_to_the_employer(
    make_applicant, job, make_application, auth_client
):
    user = make_applicant(first_name="سارا", last_name="احمدی")
    application = make_application(user, cover_letter="شماره من ۰۹۱۲۰۰۰۰۰۰۰ است")
    erase(auth_client(user))
    application.refresh_from_db()
    assert application.status == "WITHDRAWN" and application.cover_letter == ""
    assert (
        application.resume_snapshot == {"erased": True, "version": 1}
        and application.resume_id is None
    )
    last = ApplicationStatusHistory.objects.filter(application=application).last()
    assert (last.from_status, last.to_status, last.note) == (
        "PENDING",
        "WITHDRAWN",
        "Account erased",
    )

    r = auth_client(job.employer.user).get(f"/api/v1/applications/{application.pk}/")
    assert r.status_code == 200  # the employer's history stays intact...
    text = r.content.decode()
    assert "احمدی" not in text and "سارا" not in str(r.json()["resume"])  # ...without personal data


def test_final_applications_keep_their_status(make_applicant, job, make_application, auth_client):
    user = make_applicant()
    application = make_application(user)
    Application.objects.filter(pk=application.pk).update(status="ACCEPTED")
    erase(auth_client(user))
    application.refresh_from_db()
    assert application.status == "ACCEPTED" and application.resume_snapshot == {
        "erased": True,
        "version": 1,
    }


def test_proposals_are_blanked_and_withdrawn(make_applicant, project, make_proposal, auth_client):
    user = make_applicant()
    proposal = make_proposal(user, description="تماس: ۰۹۱۲۰۰۰۰۰۰۰ — پیشنهاد من برای این پروژه")
    erase(auth_client(user))
    proposal.refresh_from_db()
    assert proposal.status == "WITHDRAWN" and proposal.description == "[حذف‌شده]"
    assert (
        ProjectProposalStatusHistory.objects.filter(
            proposal=proposal, note="Account erased"
        ).count()
        == 1
    )
    assert ProjectProposal.objects.count() == 1  # the record itself stays for the employer


def test_catalogue_suggestions_are_unlinked_but_kept(make_user, auth_client):
    user = make_user()
    auth_client(user).post("/api/v1/skills/suggestions/", {"text": "Blender"}, format="json")
    erase(auth_client(user))
    suggestion = SkillSuggestion.objects.get()
    assert suggestion.suggested_by is None and suggestion.text == "Blender"


# ------------------------------------------------------------------ employer data
def test_employer_posts_disappear_and_profile_is_blanked(
    make_employer, make_post, api_client, auth_client
):
    owner = make_employer(display_name="شرکت من")
    post = make_post(employer=owner, published=True)
    assert api_client.get(f"/api/v1/jobs/{post.pk}/").status_code == 200
    erase(auth_client(owner))
    assert api_client.get(f"/api/v1/jobs/{post.pk}/").status_code == 404
    assert api_client.get("/api/v1/jobs/").json()["count"] == 0
    post.refresh_from_db()
    assert post.lifecycle_status == "DEACTIVATED" and JobPost.objects.filter(pk=post.pk).exists()
    owner.employer_profile.refresh_from_db()
    assert (
        owner.employer_profile.display_name == "حساب حذف‌شده" and owner.employer_profile.about == ""
    )


def test_sole_owner_company_is_closed(make_employer, auth_client):
    owner = make_employer()
    company = create_company(employer=owner.employer_profile, name="Solo")
    erase(auth_client(owner))
    company.refresh_from_db()
    assert company.is_active is False and CompanyMembership.objects.count() == 0


def test_owner_of_a_company_with_members_must_hand_over_first(make_employer, auth_client):
    owner, member = make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Team")
    CompanyMembership.objects.create(company=company, employer=member.employer_profile)
    r = erase(auth_client(owner))
    assert r.status_code == 409 and "Team" in r.json()["error"]["message"]
    owner.refresh_from_db()
    assert owner.is_active and Company.objects.get(pk=company.pk).is_active  # nothing was changed


def test_plain_members_can_leave_by_erasing(make_employer, auth_client):
    owner, member = make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Team")
    CompanyMembership.objects.create(company=company, employer=member.employer_profile)
    assert erase(auth_client(member)).status_code == 204
    company.refresh_from_db()
    assert company.is_active and CompanyMembership.objects.filter(company=company).count() == 1


def test_one_account_with_both_roles_is_erased_completely(
    make_applicant, make_post, job, make_application, auth_client
):
    from apps.profiles.models import EmployerProfile

    user = make_applicant()
    EmployerProfile.objects.create(user=user, display_name="هر دو نقش")
    own_post = make_post(employer=user, published=True)
    make_application(user)
    assert erase(auth_client(user)).status_code == 204
    own_post.refresh_from_db()
    assert own_post.lifecycle_status == "DEACTIVATED" and Resume.objects.count() == 0


def test_a_failed_erasure_changes_nothing(make_employer, make_applicant, auth_client, monkeypatch):
    """All-or-nothing: a crash half-way must not leave a half-erased account."""
    user = make_applicant()
    from apps.privacy import services

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(services, "blacklist_all_tokens", boom)
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user)
    assert erase(client).status_code == 500
    user.refresh_from_db()
    assert user.is_active and user.has_usable_password() and Resume.objects.count() == 1

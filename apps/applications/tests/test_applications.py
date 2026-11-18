import pytest

from apps.applications.models import Application, ApplicationStatusHistory
from apps.resumes.models import ResumeSkill

pytestmark = pytest.mark.django_db


def apply_url(pk):
    return f"/api/v1/jobs/{pk}/applications/"


def app_url(pk, tail=""):
    return f"/api/v1/applications/{pk}/{tail}"


# ------------------------------------------------------------------ submitting
def test_apply_requires_login_and_a_job_seeker_profile(
    api_client, job, make_employer, make_user, auth_client
):
    assert api_client.post(apply_url(job.pk), {}, format="json").status_code == 401
    assert (
        auth_client(make_employer()).post(apply_url(job.pk), {}, format="json").status_code == 403
    )
    assert auth_client(make_user()).post(apply_url(job.pk), {}, format="json").status_code == 403
    assert Application.objects.count() == 0


def test_apply_creates_pending_application_with_snapshot_and_history(
    job, make_applicant, auth_client
):
    user = make_applicant()
    r = auth_client(user).post(
        apply_url(job.pk), {"cover_letter": "سلام، مشتاق همکاری هستم."}, format="json"
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PENDING" and body["allowed_next_statuses"] == ["WITHDRAWN"]
    assert body["job_post"]["id"] == job.pk and body["applicant"] == {
        "first_name": "سارا",
        "last_name": "احمدی",
    }
    snap = body["resume"]
    assert snap["personal"]["first_name"] == "سارا" and snap["personal"]["city"] == "شیراز"
    assert snap["skills"] and snap["educations"] and snap["work_experiences"] and snap["languages"]
    assert snap["certificates"] and snap["portfolio_items"] and snap["desired_job_titles"]
    app = Application.objects.get()
    assert (
        app.job_seeker == user.job_seeker_profile
        and app.resume_id == user.job_seeker_profile.resume.pk
    )
    entry = ApplicationStatusHistory.objects.get(application=app)
    assert (entry.from_status, entry.to_status, entry.actor) == ("", "PENDING", user)


def test_snapshot_leaves_out_date_of_birth_and_photo(job, make_applicant, auth_client):
    snap = auth_client(make_applicant()).post(apply_url(job.pk), {}, format="json").json()["resume"]
    text = str(snap)
    assert "date_of_birth" not in snap and "photo" not in text and "1998" not in text


def test_server_controlled_fields_are_ignored(job, make_applicant, auth_client):
    victim, attacker = make_applicant(), make_applicant()
    r = auth_client(attacker).post(
        apply_url(job.pk),
        {
            "status": "ACCEPTED",
            "job_seeker": victim.job_seeker_profile.pk,
            "resume": 1,
            "resume_snapshot": {"hacked": 1},
        },
        format="json",
    )
    assert r.status_code == 201
    app = Application.objects.get()
    assert app.status == "PENDING" and app.job_seeker == attacker.job_seeker_profile
    assert "hacked" not in app.resume_snapshot


def test_resume_is_required_and_must_be_complete(job, make_applicant, make_seeker, auth_client):
    no_resume = auth_client(make_seeker()).post(apply_url(job.pk), {}, format="json")
    assert no_resume.status_code == 400 and "resume" in no_resume.json()["error"]["details"]
    incomplete = auth_client(make_applicant(complete=False)).post(
        apply_url(job.pk), {}, format="json"
    )
    assert incomplete.status_code == 400
    assert incomplete.json()["error"]["details"]["missing"] == ["desired_job_titles", "skills"]
    assert Application.objects.count() == 0


def test_cannot_apply_to_a_project_through_the_application_endpoint(
    project, make_applicant, auth_client
):
    r = auth_client(make_applicant()).post(apply_url(project.pk), {}, format="json")
    assert (
        r.status_code == 400 and "proposal" in str(r.json()["error"]["details"]["detail"]).lower()
    )
    assert Application.objects.count() == 0


@pytest.mark.parametrize("name", ["draft", "pending", "deactivated", "expired"])
def test_cannot_apply_to_posts_that_are_not_public(name, hidden_posts, make_applicant, auth_client):
    r = auth_client(make_applicant()).post(apply_url(hidden_posts[name].pk), {}, format="json")
    assert r.status_code == 404
    assert Application.objects.count() == 0


def test_unknown_post_is_404(make_applicant, auth_client):
    assert (
        auth_client(make_applicant()).post(apply_url(999999), {}, format="json").status_code == 404
    )


def test_cannot_apply_to_your_own_post(make_applicant, make_post, auth_client):
    user = make_applicant()
    from apps.profiles.models import EmployerProfile

    EmployerProfile.objects.create(user=user, display_name="Me")
    own = make_post(employer=user, published=True)
    r = auth_client(user).post(apply_url(own.pk), {}, format="json")
    assert r.status_code == 400 and Application.objects.count() == 0


def test_cover_letter_limit(job, make_applicant, auth_client):
    client = auth_client(make_applicant())
    assert (
        client.post(apply_url(job.pk), {"cover_letter": "x" * 3001}, format="json").status_code
        == 400
    )
    assert (
        client.post(apply_url(job.pk), {"cover_letter": "x" * 3000}, format="json").status_code
        == 201
    )


# ------------------------------------------------------------------ duplicates
def test_duplicate_application_is_409(job, make_applicant, auth_client):
    client = auth_client(make_applicant())
    assert client.post(apply_url(job.pk), {}, format="json").status_code == 201
    r = client.post(apply_url(job.pk), {}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert Application.objects.count() == 1


def test_still_blocked_after_rejection_but_allowed_after_withdrawal(
    job, make_applicant, auth_client, make_application
):
    user = make_applicant()
    app = make_application(user)
    client = auth_client(user)
    Application.objects.filter(pk=app.pk).update(status="REJECTED")
    assert client.post(apply_url(job.pk), {}, format="json").status_code == 409

    Application.objects.filter(pk=app.pk).update(status="PENDING")
    assert (
        client.post(
            app_url(app.pk, "transition/"), {"status": "WITHDRAWN"}, format="json"
        ).status_code
        == 200
    )
    again = client.post(apply_url(job.pk), {}, format="json")
    assert again.status_code == 201 and again.json()["id"] != app.pk
    assert Application.objects.filter(job_post=job).count() == 2
    assert client.post(apply_url(job.pk), {}, format="json").status_code == 409  # new one is active


def test_two_seekers_can_apply_to_the_same_post(job, make_applicant, auth_client):
    assert (
        auth_client(make_applicant()).post(apply_url(job.pk), {}, format="json").status_code == 201
    )
    assert (
        auth_client(make_applicant()).post(apply_url(job.pk), {}, format="json").status_code == 201
    )


# ------------------------------------------------------------------ snapshot
def test_later_resume_edits_never_change_a_submitted_application(
    job, make_applicant, make_skill, auth_client, make_application
):
    user = make_applicant()
    app = make_application(user)
    before = Application.objects.get(pk=app.pk).resume_snapshot

    client = auth_client(user)
    client.patch(
        "/api/v1/resumes/me/",
        {"introduction": "متن کاملاً جدید", "expected_monthly_salary": 99_000_000},
        format="json",
    )
    client.patch("/api/v1/profiles/job-seeker/me/", {"first_name": "نام‌جدید"}, format="json")
    ResumeSkill.objects.filter(resume__job_seeker=user.job_seeker_profile).delete()
    client.post(
        "/api/v1/resumes/me/skills/",
        {"skill": make_skill("Brand new").pk, "level": "EXPERT"},
        format="json",
    )

    owner = job.employer.user
    seen = auth_client(owner).get(app_url(app.pk)).json()["resume"]
    assert seen == before
    assert seen["introduction"] == "مسلط به جنگو" and seen["personal"]["first_name"] == "سارا"
    assert seen["expected_monthly_salary"] == 30_000_000 and len(seen["skills"]) == 1
    assert "Brand new" not in str(seen)
    assert client.get("/api/v1/resumes/me/").json()["introduction"] == "متن کاملاً جدید"


def test_deleting_the_live_resume_keeps_the_application_readable(
    job, make_applicant, auth_client, make_application
):
    user = make_applicant()
    app = make_application(user)
    user.job_seeker_profile.resume.delete()
    app.refresh_from_db()
    assert app.resume_id is None
    assert (
        auth_client(job.employer.user)
        .get(app_url(app.pk))
        .json()["resume"]["personal"]["first_name"]
        == "سارا"
    )


def test_contact_comes_from_the_resume_or_falls_back_to_the_account(
    job, make_applicant, make_application
):
    plain = make_applicant(email="plain@example.com", phone="09120000001")
    assert make_application(plain).resume_snapshot["contact"] == {
        "email": "plain@example.com",
        "phone": "09120000001",
    }
    custom = make_applicant(email="acct@example.com")
    resume = custom.job_seeker_profile.resume
    resume.contact_email, resume.contact_phone = "work@example.com", "09125550000"
    resume.save()
    assert make_application(custom).resume_snapshot["contact"] == {
        "email": "work@example.com",
        "phone": "09125550000",
    }


# ------------------------------------------------------------------ who can see what
def test_my_applications_lists_only_mine_and_filters_by_status(
    make_applicant, make_post, auth_client, make_application
):
    me, other = make_applicant(), make_applicant()
    first, second = make_post(published=True), make_post(published=True)
    a1, _ = make_application(me, first), make_application(me, second)
    make_application(other, first)
    Application.objects.filter(pk=a1.pk).update(status="REJECTED")
    client = auth_client(me)
    data = client.get("/api/v1/applications/mine/").json()
    assert data["count"] == 2 and all("resume" not in row for row in data["results"])
    assert client.get("/api/v1/applications/mine/", {"status": "REJECTED"}).json()["count"] == 1
    assert client.get("/api/v1/applications/mine/", {"status": "BOGUS"}).status_code == 400


def test_my_applications_needs_a_job_seeker(api_client, make_employer, auth_client):
    assert api_client.get("/api/v1/applications/mine/").status_code == 401
    assert auth_client(make_employer()).get("/api/v1/applications/mine/").status_code == 403


def test_owner_lists_only_applications_of_their_own_post(
    job, make_post, make_applicant, make_employer, make_seeker, auth_client, make_application
):
    a, b = make_applicant(), make_applicant()
    make_application(a)
    other_post = make_post(published=True)
    make_application(b, other_post)

    owner = auth_client(job.employer.user)
    data = owner.get(apply_url(job.pk)).json()
    assert data["count"] == 1 and "resume" not in data["results"][0]
    assert data["results"][0]["applicant"]["first_name"] == "سارا"
    assert owner.get(apply_url(job.pk), {"status": "PENDING"}).json()["count"] == 1
    assert owner.get(apply_url(job.pk), {"status": "ACCEPTED"}).json()["count"] == 0

    assert auth_client(make_employer()).get(apply_url(job.pk)).status_code == 404  # not their post
    assert auth_client(make_employer()).get(apply_url(other_post.pk)).status_code == 404
    assert auth_client(make_seeker()).get(apply_url(job.pk)).status_code == 403
    assert (
        auth_client(a).get(apply_url(job.pk)).status_code == 403
    )  # applicants cannot list applicants


def test_owner_asking_for_applications_of_a_project_is_told_to_use_proposals(project, auth_client):
    r = auth_client(project.employer.user).get(apply_url(project.pk))
    assert r.status_code == 400 and "proposals" in str(r.json()["error"]["details"]).lower()


def test_owner_can_still_see_applications_after_the_post_is_deactivated(
    job, make_applicant, auth_client, make_application
):
    make_application(make_applicant())
    from apps.jobs.models import JobPost

    JobPost.objects.filter(pk=job.pk).update(lifecycle_status="DEACTIVATED")
    assert auth_client(job.employer.user).get(apply_url(job.pk)).json()["count"] == 1


def test_detail_is_visible_only_to_the_two_parties(
    job, make_applicant, make_employer, make_seeker, api_client, auth_client, make_application
):
    applicant = make_applicant()
    app = make_application(applicant)
    assert api_client.get(app_url(app.pk)).status_code == 401
    for allowed in (applicant, job.employer.user):
        r = auth_client(allowed).get(app_url(app.pk))
        assert r.status_code == 200 and "resume" in r.json()
    for stranger in (make_applicant(), make_seeker(), make_employer()):
        assert auth_client(stranger).get(app_url(app.pk)).status_code == 404
        assert auth_client(stranger).get(app_url(app.pk, "history/")).status_code == 404
        assert (
            auth_client(stranger)
            .post(app_url(app.pk, "transition/"), {"status": "REVIEWING"}, format="json")
            .status_code
            == 404
        )


def test_employer_never_reaches_the_live_resume_of_an_applicant(
    job, make_applicant, auth_client, make_application
):
    applicant = make_applicant()
    make_application(applicant)
    owner = auth_client(job.employer.user)
    assert owner.get("/api/v1/resumes/me/").status_code == 403  # no seeker profile
    body = owner.get(apply_url(job.pk)).json()["results"][0]
    assert set(body["applicant"]) == {"first_name", "last_name"}


def test_list_queries_do_not_grow_with_rows(
    job, make_applicant, auth_client, make_application, django_assert_max_num_queries
):
    for _ in range(12):
        make_application(make_applicant())
    with django_assert_max_num_queries(6):
        r = auth_client(job.employer.user).get(apply_url(job.pk), {"page_size": 12})
    assert len(r.json()["results"]) == 12

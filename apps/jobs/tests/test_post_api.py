import datetime

import pytest

from apps.companies.services import create_company
from apps.jobs.models import EmploymentDetail, JobPost, ProjectDetail

pytestmark = pytest.mark.django_db

EMPLOYMENT = "/api/v1/jobs/employment/"
PROJECTS = "/api/v1/jobs/projects/"


def detail_url(pk):
    return f"/api/v1/jobs/{pk}/"


# ------------------------------------------------------------------ who can create
def test_only_employers_can_create(api_client, make_seeker, make_user, auth_client, payloads):
    assert api_client.post(EMPLOYMENT, payloads.employment(), format="json").status_code == 401
    assert (
        auth_client(make_seeker())
        .post(EMPLOYMENT, payloads.employment(), format="json")
        .status_code
        == 403
    )
    assert (
        auth_client(make_user()).post(PROJECTS, payloads.project(), format="json").status_code
        == 403
    )


def test_create_employment_post_is_a_draft_with_exactly_one_detail(
    make_employer, auth_client, payloads
):
    user = make_employer()
    r = auth_client(user).post(EMPLOYMENT, payloads.employment(), format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["moderation_status"] == "DRAFT" and body["is_publicly_visible"] is False
    assert body["post_type"] == "EMPLOYMENT" and "employment" in body and "project" not in body
    post = JobPost.objects.get(pk=body["id"])
    assert EmploymentDetail.objects.filter(job_post=post).count() == 1
    assert not ProjectDetail.objects.filter(job_post=post).exists()
    assert post.employer == user.employer_profile and post.search_text


def test_create_project_post(make_employer, auth_client, payloads):
    r = auth_client(make_employer()).post(PROJECTS, payloads.project(), format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["post_type"] == "PROJECT" and "project" in body and "employment" not in body
    assert body["project"]["currency"] == "IRR"


def test_wrong_detail_section_for_the_endpoint_is_rejected(make_employer, auth_client, payloads):
    client = auth_client(make_employer())
    mixed = payloads.employment(project={"budget_min": 1, "budget_max": 2})
    r = client.post(EMPLOYMENT, mixed, format="json")
    assert r.status_code == 400 and "project" in r.json()["error"]["details"]
    wrong = payloads.project()
    r2 = client.post(EMPLOYMENT, wrong, format="json")  # project body to the employment endpoint
    assert r2.status_code == 400 and "employment" in r2.json()["error"]["details"]
    assert JobPost.objects.count() == 0


def test_detail_section_is_mandatory(make_employer, auth_client, payloads):
    client = auth_client(make_employer())
    body = payloads.employment()
    del body["employment"]
    assert client.post(EMPLOYMENT, body, format="json").status_code == 400
    assert JobPost.objects.count() == 0


# ------------------------------------------------------------------ salary / budget rules
@pytest.mark.parametrize(
    "salary",
    [
        {"salary_min": 50, "salary_max": 10},
        {"salary_min": 0, "salary_max": 10},
        {"salary_min": -5, "salary_max": 10},
        {"salary_max": 10},
        {"salary_min": 10},
    ],
)
def test_salary_rules(make_employer, auth_client, payloads, salary):
    body = payloads.employment()
    body["employment"] = {"employment_type": "FULL_TIME", **salary}
    r = auth_client(make_employer()).post(EMPLOYMENT, body, format="json")
    assert r.status_code == 400
    assert JobPost.objects.count() == 0  # nothing half-created


@pytest.mark.parametrize(
    "budget",
    [
        {"budget_min": 9, "budget_max": 1},
        {"budget_min": 0, "budget_max": 1},
        {"budget_min": 1},
        {"budget_min": 1, "budget_max": 2, "currency": "EUR"},
        {"budget_min": 1, "budget_max": 2, "expected_duration_days": 0},
    ],
)
def test_budget_rules(make_employer, auth_client, payloads, budget):
    body = payloads.project()
    body["project"] = budget
    assert auth_client(make_employer()).post(PROJECTS, body, format="json").status_code == 400


def test_project_deadline_must_be_in_the_future(make_employer, auth_client, payloads):
    client = auth_client(make_employer())
    today = datetime.date.today()
    body = payloads.project()
    body["project"] = {"budget_min": 1, "budget_max": 2, "deadline": today.isoformat()}
    assert client.post(PROJECTS, body, format="json").status_code == 400
    body["project"]["deadline"] = (today + datetime.timedelta(days=20)).isoformat()
    assert client.post(PROJECTS, body, format="json").status_code == 201


# ------------------------------------------------------------------ common-field rules
def test_title_description_category_and_duration_rules(
    make_employer, auth_client, payloads, category
):
    client = auth_client(make_employer())
    assert (
        client.post(EMPLOYMENT, payloads.employment(title="abc"), format="json").status_code == 400
    )
    assert (
        client.post(EMPLOYMENT, payloads.employment(description="short"), format="json").status_code
        == 400
    )
    assert (
        client.post(EMPLOYMENT, payloads.employment(duration_days=91), format="json").status_code
        == 400
    )
    assert (
        client.post(EMPLOYMENT, payloads.employment(duration_days=0), format="json").status_code
        == 400
    )
    assert (
        client.post(EMPLOYMENT, payloads.employment(category=99999), format="json").status_code
        == 400
    )
    category.is_active = False
    category.save()
    assert client.post(EMPLOYMENT, payloads.employment(), format="json").status_code == 400


def test_location_rules(make_employer, auth_client, payloads, shiraz):
    from apps.locations.models import Province

    client = auth_client(make_employer())
    onsite = payloads.employment(work_mode="ON_SITE")
    assert client.post(EMPLOYMENT, onsite, format="json").status_code == 400  # province needed
    assert (
        client.post(EMPLOYMENT, payloads.employment(work_mode="HYBRID"), format="json").status_code
        == 400
    )

    r = client.post(
        EMPLOYMENT, payloads.employment(work_mode="ON_SITE", city=shiraz.pk), format="json"
    )
    assert (
        r.status_code == 201 and r.json()["province"]["id"] == shiraz.province_id
    )  # city implies province

    tehran = Province.objects.get(name="تهران")
    clash = payloads.employment(work_mode="ON_SITE", city=shiraz.pk, province=tehran.pk)
    assert client.post(EMPLOYMENT, clash, format="json").status_code == 400
    assert (
        client.post(EMPLOYMENT, payloads.employment(work_mode="REMOTE"), format="json").status_code
        == 201
    )


def test_skills_must_come_from_the_active_catalogue(
    make_employer, auth_client, payloads, make_skill
):
    client = auth_client(make_employer())
    django, pg = make_skill("Django"), make_skill("PostgreSQL")
    ok = payloads.employment(
        skills=[
            {"skill": django.pk, "is_required": True},
            {"skill": pg.pk, "is_required": False, "minimum_level": "ADVANCED"},
        ]
    )
    r = client.post(EMPLOYMENT, ok, format="json")
    assert r.status_code == 201 and len(r.json()["skills"]) == 2
    dup = payloads.employment(skills=[{"skill": django.pk}, {"skill": django.pk}])
    assert client.post(EMPLOYMENT, dup, format="json").status_code == 400
    assert (
        client.post(
            EMPLOYMENT, payloads.employment(skills=[{"skill": 99999}]), format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            EMPLOYMENT, payloads.employment(skills=[{"skill": "free text"}]), format="json"
        ).status_code
        == 400
    )
    many = [{"skill": make_skill(f"S{i}").pk} for i in range(21)]
    assert (
        client.post(EMPLOYMENT, payloads.employment(skills=many), format="json").status_code == 400
    )


# ------------------------------------------------------------------ mass assignment / ownership
def test_server_controlled_fields_are_ignored(make_employer, auth_client, payloads, make_post):
    victim = make_employer()
    attacker = make_employer()
    body = payloads.employment(
        moderation_status="APPROVED",
        lifecycle_status="ACTIVE",
        employer=victim.employer_profile.pk,
        post_type="PROJECT",
        published_at="2020-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        moderation_note="pre-approved",
        id=999,
    )
    r = auth_client(attacker).post(EMPLOYMENT, body, format="json")
    assert r.status_code == 201
    post = JobPost.objects.get(pk=r.json()["id"])
    assert post.employer == attacker.employer_profile
    assert post.post_type == "EMPLOYMENT" and post.moderation_status == "DRAFT"
    assert post.published_at is None and post.expires_at is None and post.moderation_note == ""
    assert post.pk != 999


def test_company_must_belong_to_the_employer(make_employer, auth_client, payloads):
    me, other = make_employer(), make_employer()
    mine = create_company(employer=me.employer_profile, name="Mine")
    theirs = create_company(employer=other.employer_profile, name="Theirs")
    client = auth_client(me)
    ok = client.post(EMPLOYMENT, payloads.employment(company=mine.pk), format="json")
    assert ok.status_code == 201 and ok.json()["company"]["name"] == "Mine"
    assert (
        client.post(EMPLOYMENT, payloads.employment(company=theirs.pk), format="json").status_code
        == 400
    )
    assert (
        client.post(EMPLOYMENT, payloads.employment(company=None), format="json").status_code == 201
    )  # optional


def test_cannot_edit_or_delete_or_act_on_another_employers_post(
    make_employer, make_post, auth_client
):
    owner, intruder = make_employer(), make_employer()
    post = make_post(employer=owner)
    client = auth_client(intruder)
    assert (
        client.patch(detail_url(post.pk), {"title": "Hacked title"}, format="json").status_code
        == 404
    )
    assert client.delete(detail_url(post.pk)).status_code == 404
    for action in ("submit", "deactivate", "activate", "renew"):
        assert client.post(f"{detail_url(post.pk)}{action}/").status_code == 404
    post.refresh_from_db()
    assert post.title != "Hacked title" and post.moderation_status == "DRAFT"


# ------------------------------------------------------------------ editing
def test_patch_updates_common_nested_and_skills(make_employer, make_post, make_skill, auth_client):
    owner = make_employer()
    post = make_post(employer=owner, skills=[make_skill("Old")])
    new_skill = make_skill("New")
    client = auth_client(owner)
    r = client.patch(
        detail_url(post.pk),
        {
            "title": "عنوان جدید آگهی",
            "employment": {"salary_max": 99_000_000},
            "skills": [{"skill": new_skill.pk, "is_required": False}],
        },
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "عنوان جدید آگهی"
    assert (
        body["employment"]["salary_max"] == 99_000_000
        and body["employment"]["salary_min"] == 10_000_000
    )
    assert [s["skill"] for s in body["skills"]] == [new_skill.pk]


def test_patch_rechecks_range_against_stored_values(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)  # salary 10M..20M
    client = auth_client(owner)
    assert (
        client.patch(
            detail_url(post.pk), {"employment": {"salary_max": 5_000_000}}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            detail_url(post.pk), {"employment": {"salary_min": 30_000_000}}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            detail_url(post.pk), {"employment": {"salary_min": 15_000_000}}, format="json"
        ).status_code
        == 200
    )


def test_patch_cannot_change_type_or_add_the_other_detail(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    client = auth_client(owner)
    r = client.patch(
        detail_url(post.pk),
        {"post_type": "PROJECT", "project": {"budget_min": 1, "budget_max": 2}},
        format="json",
    )
    assert r.status_code == 400
    post.refresh_from_db()
    assert post.post_type == "EMPLOYMENT" and not ProjectDetail.objects.exists()


def test_skills_omitted_on_patch_are_kept_empty_list_clears(
    make_employer, make_post, make_skill, auth_client
):
    owner = make_employer()
    post = make_post(employer=owner, skills=[make_skill("Keep")])
    client = auth_client(owner)
    assert (
        len(
            client.patch(detail_url(post.pk), {"title": "عنوان تازه"}, format="json").json()[
                "skills"
            ]
        )
        == 1
    )
    assert client.patch(detail_url(post.pk), {"skills": []}, format="json").json()["skills"] == []


def test_search_text_follows_edits(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner, title="عنوان قدیمی")
    auth_client(owner).patch(detail_url(post.pk), {"title": "حسابدار ارشد"}, format="json")
    post.refresh_from_db()
    assert "حسابدار" in post.search_text and "قدیمی" not in post.title_normalized


def test_my_posts_lists_only_own_posts_in_all_states(make_employer, make_post, auth_client):
    me, other = make_employer(), make_employer()
    make_post(employer=me)
    make_post(employer=me, published=True)
    make_post(employer=other)
    data = auth_client(me).get("/api/v1/jobs/mine/").json()
    assert data["count"] == 2
    only_drafts = auth_client(me).get("/api/v1/jobs/mine/", {"moderation_status": "DRAFT"}).json()
    assert only_drafts["count"] == 1
    assert (
        auth_client(me).get("/api/v1/jobs/mine/", {"moderation_status": "NOPE"}).status_code == 400
    )


def test_my_posts_needs_employer(api_client, make_seeker, auth_client):
    assert api_client.get("/api/v1/jobs/mine/").status_code == 401
    assert auth_client(make_seeker()).get("/api/v1/jobs/mine/").status_code == 403

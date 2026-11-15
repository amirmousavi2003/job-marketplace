import datetime

import pytest
from django.db import IntegrityError, transaction

from apps.locations.models import City, Province
from apps.resumes.models import Education, Resume, WorkExperience

pytestmark = pytest.mark.django_db

RESUME = "/api/v1/resumes/me/"
TODAY = datetime.date.today()


def url(section, pk=None):
    base = f"/api/v1/resumes/me/{section}/"
    return base if pk is None else f"{base}{pk}/"


@pytest.fixture
def shiraz(db):
    city = City.objects.select_related("province").get(name="شیراز")
    return city.province, city


# ---------------------------------------------------------------- access
def test_resume_requires_login(api_client):
    assert api_client.get(RESUME).status_code == 401
    assert api_client.get(url("skills")).status_code == 401


def test_resume_needs_job_seeker_profile(make_employer, make_user, auth_client):
    assert auth_client(make_employer()).get(RESUME).status_code == 403
    assert auth_client(make_user()).post(RESUME, {}, format="json").status_code == 403
    assert auth_client(make_employer()).get(url("skills")).status_code == 403


def test_get_before_creation_is_404(make_seeker, auth_client):
    r = auth_client(make_seeker()).get(RESUME)
    assert r.status_code == 404
    assert auth_client(make_seeker()).get(url("educations")).status_code == 404


def test_create_resume_once(make_seeker, auth_client):
    client = auth_client(make_seeker(first_name="Sara", last_name="Ahmadi"))
    r = client.post(RESUME, {"introduction": "سلام"}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert (body["first_name"], body["last_name"]) == ("Sara", "Ahmadi")
    assert body["completeness"] == {
        "is_complete": False,
        "missing": ["location", "desired_job_titles", "skills"],
    }
    assert client.post(RESUME, {}, format="json").status_code == 409


def test_db_enforces_one_resume_per_seeker(make_resume):
    user, _ = make_resume()
    with pytest.raises(IntegrityError), transaction.atomic():
        Resume.objects.create(job_seeker=user.job_seeker_profile)


def test_names_come_from_profile_and_are_read_only(make_resume, auth_client):
    user, _ = make_resume()
    r = auth_client(user).patch(RESUME, {"first_name": "Hacker"}, format="json")
    assert r.status_code == 200 and r.json()["first_name"] == user.job_seeker_profile.first_name


def test_cannot_inject_owner_on_create(make_seeker, make_resume, auth_client):
    victim, victim_resume = make_resume()
    attacker = make_seeker()
    r = auth_client(attacker).post(
        RESUME, {"job_seeker": victim.job_seeker_profile.pk}, format="json"
    )
    assert r.status_code == 201
    assert Resume.objects.get(job_seeker=attacker.job_seeker_profile).pk != victim_resume.pk
    assert Resume.objects.filter(job_seeker=victim.job_seeker_profile).count() == 1


# ---------------------------------------------------------------- personal info
def test_city_implies_province_and_mismatch_is_rejected(make_resume, auth_client, shiraz):
    fars, city = shiraz
    tehran = Province.objects.get(name="تهران")
    user, _ = make_resume()
    client = auth_client(user)

    ok = client.patch(RESUME, {"city": city.pk}, format="json")
    assert ok.status_code == 200 and ok.json()["province"] == fars.pk

    bad = client.patch(RESUME, {"province": tehran.pk, "city": city.pk}, format="json")
    assert bad.status_code == 400 and "city" in bad.json()["error"]["details"]

    stale = client.patch(RESUME, {"province": tehran.pk}, format="json")  # old city is in Fars
    assert stale.status_code == 400

    moved = client.patch(
        RESUME, {"city": City.objects.get(name="تهران", province=tehran).pk}, format="json"
    )
    assert moved.status_code == 200 and moved.json()["province"] == tehran.pk


def test_date_of_birth_validation(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    tomorrow = (TODAY + datetime.timedelta(days=1)).isoformat()
    assert client.patch(RESUME, {"date_of_birth": tomorrow}, format="json").status_code == 400
    assert client.patch(RESUME, {"date_of_birth": "1850-01-01"}, format="json").status_code == 400
    assert client.patch(RESUME, {"date_of_birth": "1999-05-20"}, format="json").status_code == 200


def test_preferences_validation(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    r = client.patch(
        RESUME,
        {
            "experience_level": "SENIOR",
            "employment_status": "STUDENT",
            "desired_work_modes": ["REMOTE", "HYBRID", "REMOTE"],
            "expected_monthly_salary": 300_000_000,
        },
        format="json",
    )
    assert r.status_code == 200
    assert r.json()["desired_work_modes"] == ["REMOTE", "HYBRID"]
    assert client.patch(RESUME, {"experience_level": "GOD"}, format="json").status_code == 400
    assert client.patch(RESUME, {"desired_work_modes": ["MOON"]}, format="json").status_code == 400
    assert client.patch(RESUME, {"expected_monthly_salary": 0}, format="json").status_code == 400
    assert client.patch(RESUME, {"expected_monthly_salary": -5}, format="json").status_code == 400


def test_introduction_length_limit(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    assert client.patch(RESUME, {"introduction": "x" * 2001}, format="json").status_code == 400


# ---------------------------------------------------------------- skills / titles
def test_skills_add_duplicate_inactive_and_update(make_resume, make_skill, auth_client):
    user, _ = make_resume()
    client = auth_client(user)
    skill = make_skill("Photoshop", "فتوشاپ")
    r = client.post(url("skills"), {"skill": skill.pk, "level": "ADVANCED"}, format="json")
    assert r.status_code == 201 and r.json()["skill_name_fa"] == "فتوشاپ"
    assert (
        client.post(
            url("skills"), {"skill": skill.pk, "level": "BEGINNER"}, format="json"
        ).status_code
        == 400
    )

    patched = client.patch(url("skills", r.json()["id"]), {"level": "EXPERT"}, format="json")
    assert patched.status_code == 200 and patched.json()["level"] == "EXPERT"

    hidden = make_skill("Old tool")
    hidden.is_active = False
    hidden.save()
    assert (
        client.post(
            url("skills"), {"skill": hidden.pk, "level": "BEGINNER"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(url("skills"), {"skill": 99999, "level": "BEGINNER"}, format="json").status_code
        == 400
    )
    assert (
        client.post(url("skills"), {"skill": skill.pk, "level": "NINJA"}, format="json").status_code
        == 400
    )


def test_only_catalogue_skills_allowed_no_free_text(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    r = client.post(url("skills"), {"skill": "Made up", "level": "BEGINNER"}, format="json")
    assert r.status_code == 400


def test_desired_titles_and_completeness_flow(
    make_resume, make_skill, make_title, auth_client, shiraz
):
    user, _ = make_resume()
    client = auth_client(user)
    title, skill = make_title(), make_skill()

    assert (
        client.post(url("desired-titles"), {"job_title": title.pk}, format="json").status_code
        == 201
    )
    assert (
        client.post(url("desired-titles"), {"job_title": title.pk}, format="json").status_code
        == 400
    )
    client.post(url("skills"), {"skill": skill.pk, "level": "INTERMEDIATE"}, format="json")
    missing = client.get(RESUME).json()["completeness"]["missing"]
    assert missing == ["location"]

    client.patch(RESUME, {"city": shiraz[1].pk}, format="json")
    assert client.get(RESUME).json()["completeness"] == {"is_complete": True, "missing": []}


def test_desired_titles_cannot_be_patched_only_deleted(make_resume, make_title, auth_client):
    client = auth_client(make_resume()[0])
    created = client.post(
        url("desired-titles"), {"job_title": make_title().pk}, format="json"
    ).json()
    assert client.patch(url("desired-titles", created["id"]), {}, format="json").status_code == 405
    assert client.delete(url("desired-titles", created["id"])).status_code == 204
    assert client.get(RESUME).json()["completeness"]["missing"][-2:] == [
        "desired_job_titles",
        "skills",
    ]


# ---------------------------------------------------------------- education
def test_education_crud_and_date_rules(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    body = {
        "degree": "BACHELOR",
        "field_of_study": "مهندسی کامپیوتر",
        "institution": "دانشگاه شیراز",
        "start_date": "2019-09-23",
        "end_date": None,
    }
    r = client.post(url("educations"), body, format="json")
    assert r.status_code == 201
    assert (
        client.post(
            url("educations"), {**body, "end_date": "2018-01-01"}, format="json"
        ).status_code
        == 400
    )
    future = (TODAY + datetime.timedelta(days=30)).isoformat()
    assert (
        client.post(url("educations"), {**body, "start_date": future}, format="json").status_code
        == 400
    )
    assert (
        client.post(url("educations"), {**body, "degree": "WIZARD"}, format="json").status_code
        == 400
    )
    bad_patch = client.patch(
        url("educations", r.json()["id"]), {"end_date": "2000-01-01"}, format="json"
    )
    assert bad_patch.status_code == 400  # compares with the stored start_date
    ok = client.patch(url("educations", r.json()["id"]), {"end_date": "2024-06-30"}, format="json")
    assert ok.status_code == 200
    assert client.delete(url("educations", r.json()["id"])).status_code == 204
    assert Education.objects.count() == 0


def test_db_rejects_education_with_end_before_start(make_resume):
    _, resume = make_resume()
    with pytest.raises(IntegrityError), transaction.atomic():
        Education.objects.create(
            resume=resume,
            degree="MASTER",
            field_of_study="x",
            institution="y",
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2019, 1, 1),
        )


# ---------------------------------------------------------------- work experience
WORK = {"job_title": "Developer", "company_name": "Acme", "start_date": "2021-01-01"}


def test_work_experience_crud_and_dates(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    assert client.post(url("work-experiences"), WORK, format="json").status_code == 201
    assert (
        client.post(
            url("work-experiences"), {**WORK, "end_date": "2020-01-01"}, format="json"
        ).status_code
        == 400
    )
    future = (TODAY + datetime.timedelta(days=10)).isoformat()
    assert (
        client.post(
            url("work-experiences"), {**WORK, "end_date": future}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            url("work-experiences"), {**WORK, "description": "x" * 2001}, format="json"
        ).status_code
        == 400
    )


def test_explicit_no_experience_rules_both_directions(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    assert client.patch(RESUME, {"has_no_work_experience": True}, format="json").status_code == 200
    blocked = client.post(url("work-experiences"), WORK, format="json")
    assert blocked.status_code == 400

    client.patch(RESUME, {"has_no_work_experience": False}, format="json")
    assert client.post(url("work-experiences"), WORK, format="json").status_code == 201
    r = client.patch(RESUME, {"has_no_work_experience": True}, format="json")
    assert r.status_code == 400 and "has_no_work_experience" in r.json()["error"]["details"]


def test_no_experience_does_not_block_completeness(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    client.patch(RESUME, {"has_no_work_experience": True}, format="json")
    assert "work_experience" not in str(client.get(RESUME).json()["completeness"])


# ------------------------------------------- languages, certificates, portfolio
def test_languages_unique_after_normalization(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    assert (
        client.post(
            url("languages"), {"name": "انگلیسی", "proficiency": "FLUENT"}, format="json"
        ).status_code
        == 201
    )
    assert (
        client.post(
            url("languages"), {"name": " انگلیسی ", "proficiency": "BASIC"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            url("languages"), {"name": "English", "proficiency": "FLUENT"}, format="json"
        ).status_code
        == 201
    )
    assert (
        client.post(
            url("languages"), {"name": "ترکی", "proficiency": "WRONG"}, format="json"
        ).status_code
        == 400
    )


def test_certificates_dates_and_url(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    ok = {
        "title": "ICDL",
        "issuer": "فنی و حرفه‌ای",
        "issue_date": "2022-01-01",
        "credential_url": "https://x.ir/c/1",
    }
    assert client.post(url("certificates"), ok, format="json").status_code == 201
    assert (
        client.post(
            url("certificates"), {**ok, "expiry_date": "2021-01-01"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            url("certificates"), {**ok, "credential_url": "javascript:alert(1)"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            url("certificates"), {**ok, "credential_url": "ftp://x.ir/f"}, format="json"
        ).status_code
        == 400
    )


def test_portfolio_links_must_be_web_links(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    good = client.post(
        url("portfolio"), {"title": "Site", "url": "https://example.com/p"}, format="json"
    )
    assert good.status_code == 201
    for evil in ("javascript:alert(1)", "data:text/html,<script>", "ftp://example.com", "notaurl"):
        assert (
            client.post(url("portfolio"), {"title": "x", "url": evil}, format="json").status_code
            == 400
        )


def test_section_item_limits(make_resume, auth_client):
    client = auth_client(make_resume()[0])
    for i in range(10):
        assert (
            client.post(
                url("portfolio"), {"title": f"p{i}", "url": f"https://e.com/{i}"}, format="json"
            ).status_code
            == 201
        )
    r = client.post(
        url("portfolio"), {"title": "one too many", "url": "https://e.com/x"}, format="json"
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- privacy / IDOR
def test_cannot_touch_another_users_section_items(make_resume, auth_client):
    owner, _ = make_resume()
    other, _ = make_resume()
    created = auth_client(owner).post(url("work-experiences"), WORK, format="json").json()
    attacker = auth_client(other)
    target = url("work-experiences", created["id"])
    assert attacker.get(target).status_code == 404
    assert attacker.patch(target, {"company_name": "Hacked"}, format="json").status_code == 404
    assert attacker.delete(target).status_code == 404
    assert WorkExperience.objects.get(pk=created["id"]).company_name == "Acme"
    assert attacker.get(url("work-experiences")).json() == []


def test_resume_lists_only_own_data(make_resume, make_skill, auth_client):
    a, _ = make_resume()
    b, _ = make_resume()
    skill = make_skill()
    auth_client(a).post(url("skills"), {"skill": skill.pk, "level": "EXPERT"}, format="json")
    assert auth_client(b).get(RESUME).json()["skills"] == []


def test_resume_fetch_has_bounded_query_count(
    make_resume, make_skill, make_title, auth_client, django_assert_max_num_queries
):
    user, resume = make_resume()
    client = auth_client(user)
    for i in range(6):
        client.post(
            url("skills"),
            {"skill": make_skill(f"Skill {i}").pk, "level": "BEGINNER"},
            format="json",
        )
        client.post(url("work-experiences"), {**WORK, "company_name": f"C{i}"}, format="json")
        client.post(
            url("portfolio"), {"title": f"p{i}", "url": f"https://e.com/{i}"}, format="json"
        )
    client.post(url("desired-titles"), {"job_title": make_title().pk}, format="json")
    with django_assert_max_num_queries(12):
        r = client.get(RESUME)
    assert r.status_code == 200 and len(r.json()["skills"]) == 6


def test_deleting_profile_user_deletes_resume_data(make_resume, make_skill, auth_client):
    user, resume = make_resume()
    auth_client(user).post(
        url("skills"), {"skill": make_skill().pk, "level": "BEGINNER"}, format="json"
    )
    user.delete()
    assert Resume.objects.count() == 0

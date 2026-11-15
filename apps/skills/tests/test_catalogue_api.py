import pytest

from apps.skills import services
from apps.skills.models import Skill, SkillSuggestion

pytestmark = pytest.mark.django_db

SKILLS = "/api/v1/skills/"
TITLES = "/api/v1/job-titles/"


@pytest.fixture
def catalogue(db):
    ps = services.create_entry(
        services.SKILL, name_fa="فتوشاپ", name_en="Photoshop", aliases=["Adobe Photoshop", "PS"]
    )
    ai = services.create_entry(services.SKILL, name_fa="ایلوستریتور", name_en="Illustrator")
    ecu = services.create_entry(
        services.SKILL, name_fa="تعمیر ایسیو", name_en="ECU repair", aliases=["ECU"]
    )
    fe = services.create_entry(
        services.JOB_TITLE, name_fa="توسعه‌دهنده فرانت‌اند", name_en="Frontend Developer"
    )
    return {"ps": ps, "ai": ai, "ecu": ecu, "fe": fe}


def ids(response):
    return [row["id"] for row in response.json()["results"]]


def test_catalogue_requires_login(api_client):
    assert api_client.get(SKILLS).status_code == 401
    assert api_client.get(TITLES).status_code == 401


def test_search_matches_persian_english_and_alias(make_user, auth_client, catalogue):
    client = auth_client(make_user())
    assert ids(client.get(SKILLS, {"search": "فتوشاپ"})) == [catalogue["ps"].pk]
    assert ids(client.get(SKILLS, {"search": "photoshop"})) == [catalogue["ps"].pk]
    assert ids(client.get(SKILLS, {"search": "adobe"})) == [catalogue["ps"].pk]
    assert ids(client.get(TITLES, {"search": "فرانت"})) == [catalogue["fe"].pk]


def test_search_is_normalization_tolerant(make_user, auth_client, catalogue):
    client = auth_client(make_user())
    assert ids(client.get(SKILLS, {"search": "تعمير ايسيو"})) == [
        catalogue["ecu"].pk
    ]  # Arabic letters
    assert ids(client.get(SKILLS, {"search": "  ECU REPAIR "})) == [catalogue["ecu"].pk]


def test_exact_matches_rank_first_and_no_duplicates(make_user, auth_client, catalogue):
    longer = services.create_entry(services.SKILL, name_en="PS Tools")
    client = auth_client(make_user())
    result = ids(client.get(SKILLS, {"search": "ps"}))
    assert result[0] == catalogue["ps"].pk  # exact alias "ps" beats prefix "ps tools"
    assert longer.pk in result and len(result) == len(set(result))


def test_inactive_entries_are_hidden(make_user, auth_client, catalogue):
    Skill.objects.filter(pk=catalogue["ps"].pk).update(is_active=False)
    assert ids(auth_client(make_user()).get(SKILLS, {"search": "photoshop"})) == []


def test_empty_search_lists_everything_paginated(make_user, auth_client, catalogue):
    data = auth_client(make_user()).get(SKILLS).json()
    assert data["count"] == 3 and set(data) == {"count", "next", "previous", "results"}


def test_categories_are_public(api_client):
    r = api_client.get("/api/v1/categories/", {"parent": "root"})
    assert r.status_code == 200 and len(r.json()) >= 15
    assert set(r.json()[0]) == {"id", "name_fa", "name_en", "slug", "parent"}


# ---------- suggestions ----------
def suggest(client, kind, text):
    return client.post(f"/api/v1/{kind}/suggestions/", {"text": text}, format="json")


def test_suggestion_created_pending_and_not_in_catalogue(make_user, auth_client):
    client = auth_client(make_user())
    r = suggest(client, "skills", "بلندر سه‌بعدی")
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    assert "reviewed_by" not in r.json()
    assert Skill.objects.count() == 0  # not official until approved


def test_suggestion_of_existing_term_is_rejected_with_pointer(make_user, auth_client, catalogue):
    r = suggest(auth_client(make_user()), "skills", " فتوشاپ ")
    assert r.status_code == 400
    assert str(catalogue["ps"].pk) in r.json()["error"]["details"]["text"][0]
    assert suggest(auth_client(make_user()), "skills", "ادوبی فتوشاپ ps").status_code == 201


def test_variant_spellings_of_existing_term_are_rejected(make_user, auth_client, catalogue):
    client = auth_client(make_user())
    assert suggest(client, "skills", "PHOTOSHOP").status_code == 400
    assert suggest(client, "skills", "تعمير ايسيو").status_code == 400


def test_duplicate_pending_suggestion_is_409_even_from_another_user(make_user, auth_client):
    assert suggest(auth_client(make_user()), "skills", "Blender").status_code == 201
    r = suggest(auth_client(make_user()), "skills", "blender")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize("junk", ["", "a", "123", "!!", "   "])
def test_junk_suggestions_rejected(make_user, auth_client, junk):
    assert suggest(auth_client(make_user()), "skills", junk).status_code == 400


def test_pending_cap_per_user(make_user, auth_client):
    client = auth_client(make_user())
    for i in range(10):
        assert suggest(client, "skills", f"term number {chr(97 + i)}").status_code == 201
    assert suggest(client, "skills", "term number z").status_code == 400


def test_user_sees_only_own_suggestions(make_user, auth_client):
    a, b = make_user(), make_user()
    suggest(auth_client(a), "skills", "Blender")
    suggest(auth_client(b), "skills", "Figma")
    data = auth_client(a).get("/api/v1/skills/suggestions/").json()
    assert [row["text"] for row in data["results"]] == ["Blender"]


def test_suggestions_require_login(api_client):
    assert (
        api_client.post(
            "/api/v1/skills/suggestions/", {"text": "Blender"}, format="json"
        ).status_code
        == 401
    )


# ---------- admin moderation ----------
def admin_url(kind, pk=None, action=None):
    base = f"/api/v1/admin/{kind}-suggestions/"
    return base if pk is None else f"{base}{pk}/{action}/"


@pytest.fixture
def staff(make_user):
    return make_user(is_staff=True)


def test_moderation_endpoints_are_staff_only(make_user, auth_client, api_client):
    user = make_user()
    s = suggest(auth_client(user), "skills", "Blender").json()
    assert api_client.get(admin_url("skill")).status_code == 401
    client = auth_client(user)
    assert client.get(admin_url("skill")).status_code == 403
    assert client.post(admin_url("skill", s["id"], "approve"), {}, format="json").status_code == 403
    assert (
        client.post(
            admin_url("skill", s["id"], "reject"), {"note": "no"}, format="json"
        ).status_code
        == 403
    )
    assert SkillSuggestion.objects.get(pk=s["id"]).status == "PENDING"


def test_admin_lists_pending_with_submitter(make_user, auth_client, staff):
    user = make_user("who@example.com")
    suggest(auth_client(user), "skills", "Blender")
    data = auth_client(staff).get(admin_url("skill"), {"status": "pending"}).json()
    assert data["count"] == 1 and data["results"][0]["suggested_by_email"] == "who@example.com"
    assert auth_client(staff).get(admin_url("skill"), {"status": "bogus"}).status_code == 400


def test_approve_creates_official_searchable_entry(make_user, auth_client, staff):
    user = make_user()
    s = suggest(auth_client(user), "skills", "Blender").json()
    r = auth_client(staff).post(
        admin_url("skill", s["id"], "approve"),
        {"name_fa": "بلندر", "name_en": "Blender", "aliases": ["Blender 3D"], "note": "ok"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert r.json()["resulting"]["name_en"] == "Blender"
    found = auth_client(user).get(SKILLS, {"search": "بلندر"}).json()
    assert found["count"] == 1
    assert auth_client(user).get(SKILLS, {"search": "blender 3d"}).json()["count"] == 1
    mine = auth_client(user).get("/api/v1/skills/suggestions/").json()["results"][0]
    assert mine["status"] == "APPROVED" and mine["resulting"]["id"] == found["results"][0]["id"]


def test_approve_defaults_name_by_script(auth_client, make_user, staff):
    s = suggest(auth_client(make_user()), "skills", "نقاشی دیجیتال").json()
    r = auth_client(staff).post(admin_url("skill", s["id"], "approve"), {}, format="json")
    assert r.json()["resulting"] == {
        "id": r.json()["resulting"]["id"],
        "name_fa": "نقاشی دیجیتال",
        "name_en": "",
    }


def test_approve_as_alias_of_existing_entry_creates_no_duplicate(
    make_user, auth_client, staff, catalogue
):
    s = suggest(auth_client(make_user()), "skills", "فوتوشاپ").json()
    r = auth_client(staff).post(
        admin_url("skill", s["id"], "approve"), {"existing_id": catalogue["ps"].pk}, format="json"
    )
    assert r.status_code == 200
    assert Skill.objects.count() == 3
    assert (
        auth_client(make_user()).get(SKILLS, {"search": "فوتوشاپ"}).json()["results"][0]["id"]
        == catalogue["ps"].pk
    )


def test_approve_rejects_mixed_modes_and_unknown_target(make_user, auth_client, staff, catalogue):
    s = suggest(auth_client(make_user()), "skills", "Blender").json()
    client = auth_client(staff)
    mixed = client.post(
        admin_url("skill", s["id"], "approve"),
        {"existing_id": catalogue["ps"].pk, "name_en": "Blender"},
        format="json",
    )
    assert mixed.status_code == 400
    assert (
        client.post(
            admin_url("skill", s["id"], "approve"), {"existing_id": 99999}, format="json"
        ).status_code
        == 404
    )


def test_cannot_review_twice(make_user, auth_client, staff):
    s = suggest(auth_client(make_user()), "skills", "Blender").json()
    client = auth_client(staff)
    assert client.post(admin_url("skill", s["id"], "approve"), {}, format="json").status_code == 200
    assert client.post(admin_url("skill", s["id"], "approve"), {}, format="json").status_code == 409
    assert (
        client.post(
            admin_url("skill", s["id"], "reject"), {"note": "late"}, format="json"
        ).status_code
        == 409
    )
    assert Skill.objects.count() == 1


def test_reject_needs_reason_and_keeps_catalogue_clean(make_user, auth_client, staff):
    s = suggest(auth_client(make_user()), "skills", "Blender").json()
    client = auth_client(staff)
    assert client.post(admin_url("skill", s["id"], "reject"), {}, format="json").status_code == 400
    assert (
        client.post(admin_url("skill", s["id"], "reject"), {"note": "x"}, format="json").status_code
        == 400
    )
    r = client.post(admin_url("skill", s["id"], "reject"), {"note": "Too vague"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert Skill.objects.count() == 0
    obj = SkillSuggestion.objects.get(pk=s["id"])
    assert (
        obj.reviewed_by == staff
        and obj.reviewed_at is not None
        and obj.resolution_note == "Too vague"
    )


def test_job_title_flow_end_to_end(make_user, auth_client, staff):
    user = make_user()
    s = suggest(auth_client(user), "job-titles", "کارشناس سئو").json()
    r = auth_client(staff).post(admin_url("job-title", s["id"], "approve"), {}, format="json")
    assert r.status_code == 200
    assert auth_client(user).get(TITLES, {"search": "سئو"}).json()["count"] == 1
    assert Skill.objects.count() == 0  # separate catalogue


def test_admin_unknown_suggestion_is_404(auth_client, staff):
    assert (
        auth_client(staff).post(admin_url("skill", 12345, "approve"), {}, format="json").status_code
        == 404
    )

import json

import pytest
from django.db import IntegrityError, transaction

from apps.applications.models import Application, ApplicationStatusHistory
from apps.jobs.models import JobPost, PostType
from apps.matching.models import AIMatch, EmbeddingCache

pytestmark = pytest.mark.django_db

REC = "/api/v1/matching/recommendations/"


def rows(client, **params):
    r = client.get(REC, params)
    assert r.status_code == 200, r.json()
    return r.json()["results"]


@pytest.fixture
def world(make_matching_seeker, make_post, make_skill, make_title, shiraz):
    django, photoshop, react = (
        make_skill("Django", "جنگو"),
        make_skill("Photoshop", "فتوشاپ"),
        make_skill("React", "ری‌اکت"),
    )
    title = make_title("Backend Developer", "توسعه‌دهنده بک‌اند")
    seeker = make_matching_seeker(skills=[django], titles=[title])
    good = make_post(
        title="برنامه‌نویس جنگو",
        description="توسعه API با جنگو و پستگرس برای یک استارتاپ",
        published=True,
        skills=[django],
    )
    other = make_post(
        title="طراح گرافیک",
        description="طراحی پوستر و بنر با فتوشاپ برای کمپین‌های تبلیغاتی",
        published=True,
        skills=[photoshop],
    )
    return {
        "seeker": seeker,
        "good": good,
        "other": other,
        "django": django,
        "photoshop": photoshop,
        "react": react,
    }


# ------------------------------------------------------------------ access
def test_recommendations_need_login_and_a_job_seeker(
    api_client, make_employer, make_user, auth_client
):
    assert api_client.get(REC).status_code == 401
    assert auth_client(make_employer()).get(REC).status_code == 403
    assert auth_client(make_user()).get(REC).status_code == 403


def test_a_resume_is_required(make_seeker, auth_client):
    r = auth_client(make_seeker()).get(REC)
    assert r.status_code == 400 and "resume" in r.json()["error"]["details"]


# ------------------------------------------------------------------ ranking and honesty
def test_matching_post_ranks_above_unrelated_and_unrelated_is_flagged(world, auth_client):
    data = rows(auth_client(world["seeker"]))
    assert [r["post"]["id"] for r in data] == [world["good"].pk, world["other"].pk]
    good, other = data
    assert good["score"] > 70 and good["flags"] == []
    assert other["score"] <= 40 and other["flags"] == [
        "NO_REQUIRED_SKILLS_MATCHED"
    ]  # warned, still listed
    assert any(r["code"] == "HARD_CONSTRAINT_WARNING" for r in other["reasons"])
    assert len(good["reasons"]) <= 3 and good["semantic_used"] is True


def test_response_is_labeled_assistive_and_names_the_engine(world, auth_client):
    body = auth_client(world["seeker"]).get(REC).json()
    assert body["matching"]["provider"] == "local_ngram" and body["matching"]["kind"] == "lexical"
    assert "تصمیم نهایی" in body["disclaimer"] and "دقت علمی ندارد" in body["disclaimer"]
    assert {"count", "next", "previous", "results"} <= set(body)


def test_only_public_posts_and_never_own_posts(
    world, make_post, hidden_posts, auth_client, make_employer
):
    me = world["seeker"]
    from apps.profiles.models import EmployerProfile

    EmployerProfile.objects.create(user=me, display_name="Me")
    own = make_post(employer=me, published=True)
    ids = {r["post"]["id"] for r in rows(auth_client(me))}
    assert ids == {world["good"].pk, world["other"].pk}
    assert own.pk not in ids and not ids & {p.pk for p in hidden_posts.values()}


def test_type_and_min_score_filters_and_validation(world, make_post, auth_client):
    project = make_post(
        post_type=PostType.PROJECT,
        published=True,
        title="پروژه جنگو",
        description="ساخت API با جنگو برای فروشگاه",
    )
    client = auth_client(world["seeker"])
    assert [r["post"]["id"] for r in rows(client, type="PROJECT")] == [project.pk]
    assert {r["post"]["id"] for r in rows(client, type="EMPLOYMENT")} == {
        world["good"].pk,
        world["other"].pk,
    }
    assert [r["post"]["id"] for r in rows(client, min_score=60)] == [world["good"].pk]
    for bad in ({"type": "X"}, {"min_score": "abc"}, {"min_score": 101}, {"min_score": -1}):
        assert client.get(REC, bad).status_code == 400


def test_pagination(world, make_post, auth_client):
    for _ in range(5):
        make_post(published=True)
    page = auth_client(world["seeker"]).get(REC, {"page_size": 3}).json()
    assert page["count"] == 7 and len(page["results"]) == 3 and page["next"]


def test_scores_are_sorted_high_to_low(world, make_post, auth_client):
    for _ in range(4):
        make_post(published=True)
    scores = [r["score"] for r in rows(auth_client(world["seeker"]))]
    assert scores == sorted(scores, reverse=True)


# ------------------------------------------------------------------ stored AI matches
def test_matches_are_stored_with_provider_and_explanation(world, auth_client):
    rows(auth_client(world["seeker"]))
    stored = AIMatch.objects.get(
        job_seeker=world["seeker"].job_seeker_profile, job_post=world["good"]
    )
    assert 0 <= stored.score <= 100 and stored.provider == "local_ngram" and stored.semantic_used
    assert stored.model_name.startswith("char-ngram") and stored.scoring_version == "1"
    assert stored.factors["skills"]["value"] == 1.0 and stored.explanation and stored.computed_at
    assert AIMatch.objects.count() == 2


def test_unchanged_inputs_are_not_recomputed_and_changes_are(world, auth_client, make_skill):
    client = auth_client(world["seeker"])
    rows(client)
    first = {m.job_post_id: m.computed_at for m in AIMatch.objects.all()}
    rows(client)
    assert {m.job_post_id: m.computed_at for m in AIMatch.objects.all()} == first  # untouched

    client.patch("/api/v1/resumes/me/", {"expected_monthly_salary": 900_000_000}, format="json")
    rows(client)
    after_resume = {m.job_post_id: m.computed_at for m in AIMatch.objects.all()}
    assert all(after_resume[k] > first[k] for k in first)

    client_owner = auth_client(world["good"].employer.user)
    client_owner.patch(
        f"/api/v1/jobs/{world['good'].pk}/", {"title": "برنامه‌نویس ارشد جنگو"}, format="json"
    )
    JobPost.objects.filter(pk=world["good"].pk).update(
        moderation_status="APPROVED"
    )  # keep it public
    rows(client)
    after_post = {m.job_post_id: m.computed_at for m in AIMatch.objects.all()}
    assert after_post[world["good"].pk] > after_resume[world["good"].pk]
    assert after_post[world["other"].pk] == after_resume[world["other"].pk]


def test_config_changes_invalidate_stored_scores(world, auth_client, settings):
    client = auth_client(world["seeker"])
    before = {m.job_post_id: m.score for m in (rows(client) and AIMatch.objects.all())}
    settings.MATCHING = {
        **settings.MATCHING,
        "WEIGHTS": {**settings.MATCHING["WEIGHTS"], "skills": 0.01, "work_mode": 0.99},
    }
    rows(client)
    assert {m.job_post_id: m.score for m in AIMatch.objects.all()} != before


def test_each_seeker_gets_and_stores_only_their_own_scores(
    world, make_matching_seeker, auth_client
):
    other_seeker = make_matching_seeker(skills=[world["photoshop"]])
    mine = rows(auth_client(world["seeker"]))
    theirs = rows(auth_client(other_seeker))
    assert (
        mine[0]["post"]["id"] == world["good"].pk and theirs[0]["post"]["id"] == world["other"].pk
    )
    assert AIMatch.objects.filter(job_seeker=world["seeker"].job_seeker_profile).count() == 2
    assert AIMatch.objects.filter(job_seeker=other_seeker.job_seeker_profile).count() == 2
    assert AIMatch.objects.count() == 4


def test_db_allows_one_match_row_per_pair_and_valid_scores(world):
    profile, post = world["seeker"].job_seeker_profile, world["good"]
    AIMatch.objects.create(
        job_seeker=profile,
        job_post=post,
        score=50,
        provider="none",
        scoring_version="1",
        inputs_hash="x",
        computed_at=post.created_at,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AIMatch.objects.create(
            job_seeker=profile,
            job_post=post,
            score=60,
            provider="none",
            scoring_version="1",
            inputs_hash="y",
            computed_at=post.created_at,
        )
    other = world["other"]
    with pytest.raises(IntegrityError), transaction.atomic():
        AIMatch.objects.create(
            job_seeker=profile,
            job_post=other,
            score=101,
            provider="none",
            scoring_version="1",
            inputs_hash="z",
            computed_at=post.created_at,
        )


def test_deleting_a_seekers_account_data_removes_their_matches(world, auth_client):
    rows(auth_client(world["seeker"]))
    world["seeker"].job_seeker_profile.delete()
    assert AIMatch.objects.count() == 0


# ------------------------------------------------------------------ no provider: honest fallback
def test_without_a_provider_scores_are_structured_only_and_say_so(world, auth_client, settings):
    settings.AI_EMBEDDING_PROVIDER = "none"
    body = auth_client(world["seeker"]).get(REC).json()
    assert (
        body["matching"]["provider"] == "none" and body["matching"]["semantic_available"] is False
    )
    good = body["results"][0]
    assert good["semantic_used"] is False and any(
        r["code"] == "SEMANTIC_UNAVAILABLE"
        for r in auth_client(world["seeker"])
        .get(f"/api/v1/matching/jobs/{world['good'].pk}/")
        .json()["all_reasons"]
    )
    stored = AIMatch.objects.get(job_post=world["good"])
    assert stored.provider == "none" and stored.model_name == "" and not stored.semantic_used
    assert EmbeddingCache.objects.count() == 0


def test_a_broken_provider_configuration_degrades_instead_of_failing(world, auth_client, settings):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"  # url/key/model missing
    r = auth_client(world["seeker"]).get(REC)
    assert r.status_code == 200 and r.json()["matching"]["semantic_available"] is False
    assert "API_KEY" in r.json()["matching"]["reason"]


# ------------------------------------------------------------------ network provider (background)
def test_network_embeddings_are_queued_and_scores_say_pending(
    world, auth_client, fake_neural, queued
):
    client = auth_client(world["seeker"])
    first = client.get(REC).json()["results"]
    assert all(r["semantic_used"] is False for r in first)
    assert len(queued) == 1 and len(queued[0]) == 3  # resume + 2 posts, one batch
    assert fake_neural.calls == []  # the request itself never calls the network provider
    stored = AIMatch.objects.get(job_post=world["good"])
    assert stored.provider == "none" and stored.semantic_used is False  # not claimed

    client.get(REC)
    assert len(queued) == 1  # same work is not queued again within the lock window


def test_once_vectors_exist_the_next_request_uses_them(world, auth_client, fake_neural, queued):
    client = auth_client(world["seeker"])
    client.get(REC)
    from apps.matching.embeddings import ensure_embeddings

    ensure_embeddings(fake_neural, queued[0])  # what the background worker would do
    body = client.get(REC).json()["results"]
    assert all(r["semantic_used"] for r in body)
    stored = AIMatch.objects.get(job_post=world["good"])
    assert (stored.provider, stored.model_name, stored.semantic_used) == (
        "fake_neural",
        "fake-1",
        True,
    )


def test_pending_reason_is_visible_in_the_detail_endpoint(world, auth_client, fake_neural, queued):
    detail = auth_client(world["seeker"]).get(f"/api/v1/matching/jobs/{world['good'].pk}/").json()
    assert (
        "SEMANTIC_PENDING" in [r["code"] for r in detail["all_reasons"]]
        and detail["semantic_used"] is False
    )


def test_provider_outage_never_breaks_recommendations(world, auth_client, fake_neural, queued):
    fake_neural.fail = True
    r = auth_client(world["seeker"]).get(REC)
    assert r.status_code == 200 and r.json()["results"][0]["score"] > 0


# ------------------------------------------------------------------ detail endpoint
def test_job_match_detail_has_factors_reasons_and_disclaimer(world, auth_client):
    d = auth_client(world["seeker"]).get(f"/api/v1/matching/jobs/{world['good'].pk}/").json()
    assert d["score"] > 70 and d["post"]["id"] == world["good"].pk
    assert d["factors"]["skills"]["details"]["required_matched"] == 1
    assert set(d["factors"]) == {
        "skills",
        "title",
        "experience",
        "education",
        "work_mode",
        "location",
        "salary",
    }
    assert d["all_reasons"] and d["disclaimer"] and d["matching"]["scoring_version"] == "1"
    assert any(r["code"] == "SKILL_OVERLAP_STRONG" for r in d["all_reasons"])


def test_detail_only_for_public_posts_and_seekers(
    world, hidden_posts, api_client, auth_client, make_employer
):
    client = auth_client(world["seeker"])
    for post in hidden_posts.values():
        assert client.get(f"/api/v1/matching/jobs/{post.pk}/").status_code == 404
    assert client.get("/api/v1/matching/jobs/999999/").status_code == 404
    assert api_client.get(f"/api/v1/matching/jobs/{world['good'].pk}/").status_code == 401
    assert (
        auth_client(make_employer()).get(f"/api/v1/matching/jobs/{world['good'].pk}/").status_code
        == 403
    )


def test_project_posts_are_scored_without_employment_only_factors(world, make_post, auth_client):
    project = make_post(post_type=PostType.PROJECT, published=True, skills=[world["django"]])
    d = auth_client(world["seeker"]).get(f"/api/v1/matching/jobs/{project.pk}/").json()
    for name in ("experience", "education", "salary"):
        assert d["factors"][name] == {"applicable": False}
    assert d["factors"]["skills"]["applicable"] is True


# ------------------------------------------------------------------ recompute / status
def test_recompute_reports_what_happened(world, auth_client, settings, fake_neural, queued):
    client = auth_client(world["seeker"])
    pending = client.post("/api/v1/matching/recompute/")
    assert (
        pending.status_code == 200
        and pending.json()["semantic"] == "pending"
        and pending.json()["matches"] == 2
    )


def test_recompute_with_local_and_without_provider(world, auth_client, settings):
    client = auth_client(world["seeker"])
    assert client.post("/api/v1/matching/recompute/").json()["semantic"] == "used"
    settings.AI_EMBEDDING_PROVIDER = "none"
    assert client.post("/api/v1/matching/recompute/").json()["semantic"] == "unavailable"


def test_recompute_needs_a_job_seeker(api_client, make_employer, auth_client):
    assert api_client.post("/api/v1/matching/recompute/").status_code == 401
    assert auth_client(make_employer()).post("/api/v1/matching/recompute/").status_code == 403


def test_status_endpoint_needs_login_and_hides_secrets(
    api_client, make_user, auth_client, settings
):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"
    settings.AI_EMBEDDING_API_URL = "https://ai.example.ir/v1"
    settings.AI_EMBEDDING_API_KEY = "sk-top-secret"
    settings.AI_EMBEDDING_MODEL = "emb"
    assert api_client.get("/api/v1/matching/status/").status_code == 401
    text = json.dumps(auth_client(make_user()).get("/api/v1/matching/status/").json())
    assert (
        "sk-top-secret" not in text
        and "ai.example.ir" not in text
        and '"openai_compatible"' in text
    )


# ------------------------------------------------------------------ assistive only
def test_matching_never_changes_any_application_or_history(
    world, job, make_applicant, make_application, auth_client
):
    applicant = make_applicant()
    application = make_application(applicant)
    before = (
        list(Application.objects.values_list("id", "status", "updated_at")),
        ApplicationStatusHistory.objects.count(),
    )
    owner, seeker = auth_client(job.employer.user), auth_client(applicant)
    seeker.get(REC)
    seeker.post("/api/v1/matching/recompute/")
    seeker.get(f"/api/v1/matching/jobs/{job.pk}/")
    owner.get(f"/api/v1/matching/jobs/{job.pk}/candidates/")
    after = (
        list(Application.objects.values_list("id", "status", "updated_at")),
        ApplicationStatusHistory.objects.count(),
    )
    assert before == after and Application.objects.get(pk=application.pk).status == "PENDING"


def test_there_is_no_way_to_decide_through_matching(world, job, auth_client):
    """Matching endpoints are read-only: no method can accept, reject or change anything."""
    owner = auth_client(job.employer.user)
    for method in ("post", "patch", "put", "delete"):
        r = getattr(owner, method)(
            f"/api/v1/matching/jobs/{job.pk}/candidates/", {"status": "ACCEPTED"}, format="json"
        )
        assert r.status_code == 405
    seeker = auth_client(world["seeker"])
    for method in ("post", "patch", "put", "delete"):
        assert getattr(seeker, method)(REC, {}, format="json").status_code == 405


def test_recommendations_query_count_is_bounded(
    world, make_post, auth_client, django_assert_max_num_queries
):
    for _ in range(30):
        make_post(published=True, skills=[world["django"]])
    client = auth_client(world["seeker"])
    client.get(REC)  # warm: creates vectors and rows
    with django_assert_max_num_queries(18):
        r = client.get(REC, {"page_size": 50})
    assert r.json()["count"] == 32

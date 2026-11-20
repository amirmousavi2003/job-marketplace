import json

import pytest

from apps.applications.models import Application
from apps.matching.models import AIMatch
from apps.matching.tasks import embed_post
from apps.moderation import services as moderation

pytestmark = pytest.mark.django_db


def cand_url(pk):
    return f"/api/v1/matching/jobs/{pk}/candidates/"


@pytest.fixture
def applicants(make_post, make_skill, make_matching_seeker, make_application, make_employer):
    """One employment post requiring Django, three applicants of different fit."""
    django, photoshop = make_skill("Django", "جنگو"), make_skill("Photoshop", "فتوشاپ")
    employer = make_employer()
    post = make_post(
        employer=employer,
        published=True,
        title="برنامه‌نویس جنگو",
        description="توسعه API با جنگو و پستگرس",
        skills=[django],
    )
    best = make_matching_seeker(skills=[django])
    weak = make_matching_seeker(skills=[photoshop])
    mid = make_matching_seeker(skills=[django, photoshop], experience_level="JUNIOR")
    # complete resumes need a desired title to be allowed to apply
    from apps.resumes.models import DesiredJobTitle
    from apps.skills import services as catalogue

    title = catalogue.create_entry(catalogue.JOB_TITLE, name_en="Dev", name_fa="توسعه‌دهنده")
    for user in (best, weak, mid):
        DesiredJobTitle.objects.create(resume=user.job_seeker_profile.resume, job_title=title)
    apps = {
        name: make_application(user, post)
        for name, user in (("weak", weak), ("best", best), ("mid", mid))
    }
    return {
        "post": post,
        "employer": employer,
        "users": {"best": best, "weak": weak, "mid": mid},
        "apps": apps,
        "django": django,
    }


def test_candidates_are_ordered_by_compatibility(applicants, auth_client):
    r = auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk))
    assert r.status_code == 200
    body = r.json()
    order = [row["application_id"] for row in body["results"]]
    assert order[0] == applicants["apps"]["best"].pk and order[-1] == applicants["apps"]["weak"].pk
    scores = [row["score"] for row in body["results"]]
    assert scores == sorted(scores, reverse=True) and scores[0] > scores[-1]
    assert body["matching"]["provider"] == "local_ngram" and "تصمیم نهایی" in body["disclaimer"]


def test_nobody_is_filtered_out_and_weak_fits_are_only_warned(applicants, auth_client):
    rows = (
        auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk)).json()["results"]
    )
    assert len(rows) == 3  # everyone who applied is listed
    weak = next(r for r in rows if r["application_id"] == applicants["apps"]["weak"].pk)
    assert weak["flags"] == ["NO_REQUIRED_SKILLS_MATCHED"] and weak["score"] <= 40
    assert weak["reasons"][0]["code"] == "HARD_CONSTRAINT_WARNING"


def test_rows_show_name_and_status_but_no_contact_details(applicants, auth_client):
    body = auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk)).json()
    text = json.dumps(body, ensure_ascii=False)
    for user in applicants["users"].values():
        assert user.email not in text
    assert "contact" not in text and "phone" not in text
    first = body["results"][0]
    assert set(first["applicant"]) == {"first_name", "last_name"} and first["status"] == "PENDING"


def test_only_the_owner_can_rank_their_applicants(
    applicants, api_client, auth_client, make_employer, make_seeker
):
    url = cand_url(applicants["post"].pk)
    assert api_client.get(url).status_code == 401
    assert auth_client(make_employer()).get(url).status_code == 404
    assert auth_client(make_seeker()).get(url).status_code == 403
    assert (
        auth_client(applicants["users"]["best"]).get(url).status_code == 403
    )  # applicants cannot rank others
    assert auth_client(applicants["employer"]).get(cand_url(999999)).status_code == 404


def test_projects_have_no_resumes_to_compare(project, auth_client):
    r = auth_client(project.employer.user).get(cand_url(project.pk))
    assert r.status_code == 400


def test_ranking_uses_the_frozen_submission_not_the_live_resume(applicants, auth_client):
    client = auth_client(applicants["employer"])
    before = {
        r["application_id"]: r["score"]
        for r in client.get(cand_url(applicants["post"].pk)).json()["results"]
    }
    weak_user = applicants["users"]["weak"]
    # the weak applicant now edits the live resume to look perfect
    from apps.resumes.models import ResumeSkill

    ResumeSkill.objects.create(
        resume=weak_user.job_seeker_profile.resume, skill=applicants["django"], level="EXPERT"
    )
    auth_client(weak_user).patch(
        "/api/v1/resumes/me/", {"introduction": "جنگو جنگو جنگو توسعه API"}, format="json"
    )
    after = {
        r["application_id"]: r["score"]
        for r in client.get(cand_url(applicants["post"].pk)).json()["results"]
    }
    assert after == before


def test_ranking_is_not_stored_and_changes_nothing(applicants, auth_client):
    snapshot = list(Application.objects.values_list("id", "status", "updated_at"))
    auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk))
    assert AIMatch.objects.count() == 0  # employer-side ranking is computed on the fly
    assert list(Application.objects.values_list("id", "status", "updated_at")) == snapshot


def test_applicants_of_other_posts_are_not_mixed_in(
    applicants, make_post, make_application, make_matching_seeker, auth_client
):
    other_post = make_post(employer=applicants["employer"], published=True)
    stranger = make_matching_seeker(skills=[applicants["django"]])
    from apps.resumes.models import DesiredJobTitle
    from apps.skills.models import JobTitle

    DesiredJobTitle.objects.create(
        resume=stranger.job_seeker_profile.resume, job_title=JobTitle.objects.first()
    )
    foreign = make_application(stranger, other_post)
    ids = {
        r["application_id"]
        for r in auth_client(applicants["employer"])
        .get(cand_url(applicants["post"].pk))
        .json()["results"]
    }
    assert foreign.pk not in ids and len(ids) == 3


def test_candidates_without_a_provider_are_structured_only(applicants, auth_client, settings):
    settings.AI_EMBEDDING_PROVIDER = "none"
    body = auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk)).json()
    assert body["matching"]["semantic_available"] is False
    assert all(row["semantic_used"] is False for row in body["results"])


def test_candidates_queue_embeddings_for_a_network_provider_and_say_pending(
    applicants, auth_client, fake_neural, queued
):
    body = auth_client(applicants["employer"]).get(cand_url(applicants["post"].pk)).json()
    assert all(row["semantic_used"] is False for row in body["results"]) and fake_neural.calls == []
    assert len(queued) == 1 and len(queued[0]) == 4  # post + 3 submitted resumes


def test_candidate_list_query_count_is_bounded(
    applicants, auth_client, django_assert_max_num_queries
):
    client = auth_client(applicants["employer"])
    client.get(cand_url(applicants["post"].pk))
    with django_assert_max_num_queries(10):
        assert client.get(cand_url(applicants["post"].pk)).status_code == 200


# ------------------------------------------------------------------ approval hook
def test_approving_a_post_queues_its_embedding_after_commit(
    make_employer, make_post, staff, monkeypatch, django_capture_on_commit_callbacks
):
    queued_ids = []
    monkeypatch.setattr(embed_post, "delay", lambda post_id: queued_ids.append(post_id))
    owner = make_employer()
    post = make_post(employer=owner)
    moderation.submit_for_review(post, actor=owner)
    with django_capture_on_commit_callbacks(execute=True):
        moderation.approve(post, reviewer=staff)
    assert queued_ids == [post.pk]


def test_nothing_is_queued_before_commit_or_on_rejection(
    make_employer, make_post, staff, monkeypatch, django_capture_on_commit_callbacks
):
    queued_ids = []
    monkeypatch.setattr(embed_post, "delay", lambda post_id: queued_ids.append(post_id))
    owner = make_employer()
    post = make_post(employer=owner)
    moderation.submit_for_review(post, actor=owner)
    with django_capture_on_commit_callbacks(execute=False):
        moderation.approve(post, reviewer=staff)
    assert queued_ids == []  # callback registered but the transaction has not committed

    other = make_post(employer=owner)
    moderation.submit_for_review(other, actor=owner)
    with django_capture_on_commit_callbacks(execute=True):
        moderation.reject(other, reviewer=staff, reason="دلیل رد")
    assert queued_ids == []

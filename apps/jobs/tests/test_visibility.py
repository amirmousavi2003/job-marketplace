import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.companies.services import create_company
from apps.jobs.models import JobPost, LifecycleStatus
from apps.jobs.selectors import visible_posts

pytestmark = pytest.mark.django_db

LIST = "/api/v1/jobs/"


def detail(pk):
    return f"/api/v1/jobs/{pk}/"


def public_ids(client):
    return {row["id"] for row in client.get(LIST).json()["results"]}


@pytest.fixture
def states(make_employer, make_post, staff):
    """One post in every non-public state, plus one public post."""
    from apps.moderation import services as m

    owner = make_employer()
    posts = {"public": make_post(employer=owner, published=True)}
    posts["draft"] = make_post(employer=owner)
    pending = make_post(employer=owner)
    m.submit_for_review(pending, actor=owner)
    posts["pending"] = pending
    rejected = make_post(employer=owner)
    m.submit_for_review(rejected, actor=owner)
    m.reject(rejected, reviewer=staff, reason="نامناسب")
    posts["rejected"] = rejected
    deactivated = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=deactivated.pk).update(lifecycle_status="DEACTIVATED")
    posts["deactivated"] = deactivated
    expired = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=expired.pk).update(
        expires_at=timezone.now() - datetime.timedelta(minutes=1)
    )
    posts["expired_lazily"] = expired  # lifecycle still ACTIVE, but past its date
    marked = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=marked.pk).update(lifecycle_status="EXPIRED")
    posts["expired_marked"] = marked
    return owner, posts


def test_only_the_approved_active_unexpired_post_is_public(api_client, states):
    _, posts = states
    assert public_ids(api_client) == {posts["public"].pk}
    assert {p.pk for p in visible_posts()} == {posts["public"].pk}


@pytest.mark.parametrize(
    "name", ["draft", "pending", "rejected", "deactivated", "expired_lazily", "expired_marked"]
)
def test_hidden_posts_are_404_for_the_public_and_other_users(
    name, api_client, auth_client, make_employer, make_seeker, states
):
    _, posts = states
    pk = posts[name].pk
    assert api_client.get(detail(pk)).status_code == 404
    assert auth_client(make_employer()).get(detail(pk)).status_code == 404
    assert auth_client(make_seeker()).get(detail(pk)).status_code == 404


@pytest.mark.parametrize("name", ["draft", "pending", "rejected", "deactivated", "expired_lazily"])
def test_owner_still_sees_hidden_posts_with_state(name, auth_client, states):
    owner, posts = states
    r = auth_client(owner).get(detail(posts[name].pk))
    assert r.status_code == 200 and r.json()["is_publicly_visible"] is False


@pytest.mark.parametrize("path", ["employment/", "projects/", ""])
def test_hidden_posts_never_leak_through_any_list_or_filter(path, api_client, states):
    _, posts = states
    hidden = {p.pk for k, p in posts.items() if k != "public"}
    for params in (
        {},
        {"q": "آگهی"},
        {"ordering": "-expires_at"},
        {"category": posts["draft"].category_id},
        {"work_mode": "REMOTE"},
    ):
        rows = api_client.get(f"/api/v1/jobs/{path}", params).json()["results"]
        assert hidden.isdisjoint({r["id"] for r in rows})


def test_public_serializer_leaks_no_private_or_moderation_data(api_client, make_post):
    post = make_post(published=True)
    body = api_client.get(detail(post.pk)).json()
    forbidden = {
        "moderation_status",
        "lifecycle_status",
        "moderation_note",
        "moderation_history",
        "employer_info",
        "duration_days",
        "is_publicly_visible",
        "created_at",
        "updated_at",
    }
    assert forbidden.isdisjoint(body)
    assert set(body["employer"]) == {"id", "display_name"}
    text = str(body)
    assert post.employer.user.email not in text and "password" not in text


def test_list_rows_use_excerpt_not_full_description(api_client, make_post):
    make_post(published=True, description="ک" * 500)
    row = api_client.get(LIST).json()["results"][0]
    assert "description" not in row and len(row["description_excerpt"]) <= 301


def test_posts_of_deactivated_accounts_and_companies_are_hidden(
    api_client, make_employer, make_post
):
    owner = make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    with_company = make_post(employer=owner, published=True, company=company)
    plain = make_post(employer=owner, published=True)
    assert public_ids(api_client) == {with_company.pk, plain.pk}
    company.is_active = False
    company.save()
    assert public_ids(api_client) == {plain.pk}
    owner.is_active = False
    owner.save()
    assert public_ids(api_client) == set()
    assert api_client.get(detail(plain.pk)).status_code == 404


def test_public_endpoints_need_no_login(api_client, make_post):
    post = make_post(published=True)
    assert api_client.get(LIST).status_code == 200
    assert api_client.get(detail(post.pk)).status_code == 200
    assert api_client.get("/api/v1/jobs/employment/").status_code == 200
    assert api_client.get("/api/v1/jobs/projects/").status_code == 200


# ------------------------------------------------------------------ lifecycle (employer actions)
def test_deactivate_and_activate_cycle(make_employer, make_post, auth_client, api_client):
    owner = make_employer()
    post = make_post(employer=owner, published=True)
    client = auth_client(owner)
    r = client.post(f"{detail(post.pk)}deactivate/")
    assert r.status_code == 200 and r.json()["lifecycle_status"] == "DEACTIVATED"
    assert api_client.get(detail(post.pk)).status_code == 404
    assert client.post(f"{detail(post.pk)}deactivate/").status_code == 409
    assert client.post(f"{detail(post.pk)}activate/").json()["is_publicly_visible"] is True
    assert api_client.get(detail(post.pk)).status_code == 200
    assert client.post(f"{detail(post.pk)}activate/").status_code == 409


def test_cannot_deactivate_or_activate_unapproved_posts(make_employer, make_post, auth_client):
    owner = make_employer()
    draft = make_post(employer=owner)
    client = auth_client(owner)
    for action in ("deactivate", "activate", "renew"):
        assert client.post(f"{detail(draft.pk)}{action}/").status_code == 409


def test_expiry_job_marks_overdue_posts_and_renew_brings_them_back(
    make_employer, make_post, auth_client, api_client
):
    owner = make_employer()
    post = make_post(employer=owner, published=True, duration_days=10)
    fresh = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=post.pk).update(
        expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    call_command("expire_jobs")
    post.refresh_from_db()
    fresh.refresh_from_db()
    assert (
        post.lifecycle_status == LifecycleStatus.EXPIRED
        and fresh.lifecycle_status == LifecycleStatus.ACTIVE
    )

    client = auth_client(owner)
    assert client.post(f"{detail(post.pk)}activate/").status_code == 409  # expired: must renew
    r = client.post(f"{detail(post.pk)}renew/")
    assert r.status_code == 200 and r.json()["is_publicly_visible"] is True
    post.refresh_from_db()
    assert post.expires_at > timezone.now() + datetime.timedelta(days=9)
    assert api_client.get(detail(post.pk)).status_code == 200


def test_delete_only_for_draft_or_rejected(make_employer, make_post, auth_client):
    owner = make_employer()
    draft, live = make_post(employer=owner), make_post(employer=owner, published=True)
    client = auth_client(owner)
    assert client.delete(detail(live.pk)).status_code == 409
    assert JobPost.objects.filter(pk=live.pk).exists()
    assert client.delete(detail(draft.pk)).status_code == 204
    assert not JobPost.objects.filter(pk=draft.pk).exists()

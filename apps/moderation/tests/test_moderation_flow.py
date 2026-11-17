import datetime

import pytest
from django.utils import timezone

from apps.moderation.models import ModerationHistory

pytestmark = pytest.mark.django_db


def post_url(pk, action=""):
    return f"/api/v1/jobs/{pk}/{action}"


def admin_url(pk=None, action=""):
    base = "/api/v1/admin/jobs/"
    return base if pk is None else f"{base}{pk}/{action}"


# ------------------------------------------------------------------ employer side
def test_submit_moves_draft_to_pending_and_logs_it(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    r = auth_client(owner).post(post_url(post.pk, "submit/"))
    assert r.status_code == 200 and r.json()["moderation_status"] == "PENDING_REVIEW"
    entry = ModerationHistory.objects.get(job_post=post)
    assert (entry.from_status, entry.to_status, entry.actor) == ("DRAFT", "PENDING_REVIEW", owner)


def test_cannot_submit_twice_or_when_approved(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    client = auth_client(owner)
    client.post(post_url(post.pk, "submit/"))
    assert client.post(post_url(post.pk, "submit/")).status_code == 409
    approved = make_post(employer=owner, published=True)
    assert client.post(post_url(approved.pk, "submit/")).status_code == 409


def test_pending_cap_per_employer(make_employer, make_post, auth_client):
    owner = make_employer()
    client = auth_client(owner)
    for _ in range(10):
        assert client.post(post_url(make_post(employer=owner).pk, "submit/")).status_code == 200
    assert client.post(post_url(make_post(employer=owner).pk, "submit/")).status_code == 400


def test_employer_cannot_publish_own_post_by_any_route(
    make_employer, make_post, auth_client, api_client
):
    owner = make_employer()
    post = make_post(employer=owner)
    client = auth_client(owner)
    client.post(post_url(post.pk, "submit/"))
    # no approve endpoint for employers, admin endpoints are staff-only
    assert client.post(admin_url(post.pk, "approve/"), {}, format="json").status_code == 403
    assert (
        client.patch(
            post_url(post.pk), {"moderation_status": "APPROVED"}, format="json"
        ).status_code
        == 200
    )
    post.refresh_from_db()
    assert post.moderation_status == "PENDING_REVIEW"
    assert api_client.get(post_url(post.pk)).status_code == 404


# ------------------------------------------------------------------ admin side
def test_admin_endpoints_are_staff_only(
    api_client, make_employer, make_seeker, make_post, auth_client
):
    post = make_post()
    for who in (api_client, auth_client(make_employer()), auth_client(make_seeker())):
        status = 401 if who is api_client else 403
        assert who.get(admin_url()).status_code == status
        assert who.get(admin_url(post.pk)).status_code == status
        assert who.post(admin_url(post.pk, "approve/"), {}, format="json").status_code == status
        assert (
            who.post(admin_url(post.pk, "reject/"), {"reason": "xxx"}, format="json").status_code
            == status
        )
        assert who.get(admin_url(post.pk, "moderation-history/")).status_code == status


def test_review_queue_lists_pending_oldest_first(make_employer, make_post, staff, auth_client):
    owner = make_employer()
    first, second = make_post(employer=owner), make_post(employer=owner)
    make_post(employer=owner)  # stays a draft
    client = auth_client(owner)
    client.post(post_url(first.pk, "submit/"))
    client.post(post_url(second.pk, "submit/"))
    data = auth_client(staff).get(admin_url(), {"moderation_status": "PENDING_REVIEW"}).json()
    assert [row["id"] for row in data["results"]] == [first.pk, second.pk]
    assert {"employer_name", "employer_email", "moderation_status"} <= set(data["results"][0])


def test_approve_publishes_and_sets_dates(make_employer, make_post, staff, auth_client, api_client):
    owner = make_employer()
    post = make_post(employer=owner, duration_days=45)
    auth_client(owner).post(post_url(post.pk, "submit/"))
    r = auth_client(staff).post(admin_url(post.pk, "approve/"), {"note": "ok"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["moderation_status"] == "APPROVED" and body["is_publicly_visible"] is True
    post.refresh_from_db()
    assert abs(
        (post.expires_at - post.published_at) - datetime.timedelta(days=45)
    ) < datetime.timedelta(seconds=2)
    assert api_client.get(post_url(post.pk)).status_code == 200
    entry = ModerationHistory.objects.filter(job_post=post).last()
    assert (entry.to_status, entry.actor, entry.note) == ("APPROVED", staff, "ok")


def test_reject_requires_reason_and_owner_sees_it(
    make_employer, make_post, staff, auth_client, api_client
):
    owner = make_employer()
    post = make_post(employer=owner)
    auth_client(owner).post(post_url(post.pk, "submit/"))
    admin = auth_client(staff)
    assert admin.post(admin_url(post.pk, "reject/"), {}, format="json").status_code == 400
    assert (
        admin.post(admin_url(post.pk, "reject/"), {"reason": "ab"}, format="json").status_code
        == 400
    )
    assert (
        admin.post(admin_url(post.pk, "reject/"), {"reason": "   "}, format="json").status_code
        == 400
    )
    r = admin.post(admin_url(post.pk, "reject/"), {"reason": "توضیحات ناکافی است"}, format="json")
    assert r.status_code == 200 and r.json()["moderation_status"] == "REJECTED"
    mine = auth_client(owner).get(post_url(post.pk)).json()
    assert mine["moderation_note"] == "توضیحات ناکافی است"
    assert api_client.get(post_url(post.pk)).status_code == 404


def test_only_pending_posts_can_be_reviewed(make_employer, make_post, staff, auth_client):
    owner = make_employer()
    draft = make_post(employer=owner)
    approved = make_post(employer=owner, published=True)
    admin = auth_client(staff)
    for post in (draft, approved):
        assert admin.post(admin_url(post.pk, "approve/"), {}, format="json").status_code == 409
        assert (
            admin.post(
                admin_url(post.pk, "reject/"), {"reason": "no good"}, format="json"
            ).status_code
            == 409
        )
    assert admin.post(admin_url(99999, "approve/"), {}, format="json").status_code == 404


def test_reviewing_twice_is_a_conflict_and_logs_once(make_employer, make_post, staff, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    auth_client(owner).post(post_url(post.pk, "submit/"))
    admin = auth_client(staff)
    assert admin.post(admin_url(post.pk, "approve/"), {}, format="json").status_code == 200
    assert admin.post(admin_url(post.pk, "approve/"), {}, format="json").status_code == 409
    assert (
        admin.post(admin_url(post.pk, "reject/"), {"reason": "late"}, format="json").status_code
        == 409
    )
    assert ModerationHistory.objects.filter(job_post=post, to_status="APPROVED").count() == 1


# ------------------------------------------------------------------ edits re-enter moderation
def test_editing_an_approved_post_sends_it_back_to_review_and_hides_it(
    make_employer, make_post, staff, auth_client, api_client
):
    owner = make_employer()
    post = make_post(employer=owner, published=True)
    assert api_client.get(post_url(post.pk)).status_code == 200
    r = auth_client(owner).patch(post_url(post.pk), {"title": "عنوان ویرایش‌شده"}, format="json")
    assert r.status_code == 200 and r.json()["moderation_status"] == "PENDING_REVIEW"
    assert api_client.get(post_url(post.pk)).status_code == 404  # hidden until re-approved
    assert ModerationHistory.objects.filter(job_post=post).last().note == "Edited after approval"

    assert (
        auth_client(staff).post(admin_url(post.pk, "approve/"), {}, format="json").status_code
        == 200
    )
    assert api_client.get(post_url(post.pk)).status_code == 200


def test_editing_a_rejected_post_returns_it_to_draft_then_resubmit(
    make_employer, make_post, staff, auth_client
):
    owner = make_employer()
    post = make_post(employer=owner)
    client = auth_client(owner)
    client.post(post_url(post.pk, "submit/"))
    auth_client(staff).post(
        admin_url(post.pk, "reject/"), {"reason": "نیاز به اصلاح"}, format="json"
    )
    r = client.patch(post_url(post.pk), {"title": "عنوان اصلاح‌شده"}, format="json")
    assert r.json()["moderation_status"] == "DRAFT"
    assert client.post(post_url(post.pk, "submit/")).json()["moderation_status"] == "PENDING_REVIEW"
    statuses = [
        (h.from_status, h.to_status) for h in ModerationHistory.objects.filter(job_post=post)
    ]
    assert statuses == [
        ("DRAFT", "PENDING_REVIEW"),
        ("PENDING_REVIEW", "REJECTED"),
        ("REJECTED", "DRAFT"),
        ("DRAFT", "PENDING_REVIEW"),
    ]


def test_editing_draft_or_pending_keeps_status(make_employer, make_post, auth_client):
    owner = make_employer()
    draft, pending = make_post(employer=owner), make_post(employer=owner)
    client = auth_client(owner)
    client.post(post_url(pending.pk, "submit/"))
    assert (
        client.patch(post_url(draft.pk), {"title": "تغییر عنوان"}, format="json").json()[
            "moderation_status"
        ]
        == "DRAFT"
    )
    assert (
        client.patch(post_url(pending.pk), {"title": "تغییر عنوان"}, format="json").json()[
            "moderation_status"
        ]
        == "PENDING_REVIEW"
    )
    assert ModerationHistory.objects.filter(job_post=draft).count() == 0


# ------------------------------------------------------------------ admin review data
def test_admin_detail_shows_employer_info_and_history(make_employer, make_post, staff, auth_client):
    owner = make_employer(display_name="کارفرمای نمونه", phone="09121234567")
    approved = make_post(employer=owner, published=True)
    rejected = make_post(employer=owner)
    target = make_post(employer=owner)
    client = auth_client(owner)
    client.post(post_url(rejected.pk, "submit/"))
    auth_client(staff).post(admin_url(rejected.pk, "reject/"), {"reason": "نامناسب"}, format="json")
    client.post(post_url(target.pk, "submit/"))

    body = auth_client(staff).get(admin_url(target.pk)).json()
    info = body["employer_info"]
    assert (
        info["display_name"] == "کارفرمای نمونه"
        and info["email"] == owner.email
        and info["phone"] == "09121234567"
    )
    assert (info["posts_total"], info["posts_approved"], info["posts_rejected"]) == (3, 1, 1)
    assert [h["to_status"] for h in body["moderation_history"]] == ["PENDING_REVIEW"]
    assert approved.pk != target.pk


def test_history_endpoint_is_ordered_and_names_actors(make_employer, make_post, staff, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    auth_client(owner).post(post_url(post.pk, "submit/"))
    auth_client(staff).post(admin_url(post.pk, "approve/"), {"note": "خوب"}, format="json")
    rows = auth_client(staff).get(admin_url(post.pk, "moderation-history/")).json()
    assert [(r["from_status"], r["to_status"], r["actor_email"]) for r in rows] == [
        ("DRAFT", "PENDING_REVIEW", owner.email),
        ("PENDING_REVIEW", "APPROVED", staff.email),
    ]
    assert auth_client(staff).get(admin_url(99999, "moderation-history/")).status_code == 404


def test_history_is_append_only_in_django_admin(make_post, staff):
    from django.contrib import admin as dj_admin

    from apps.moderation.models import ModerationHistory

    model_admin = dj_admin.site._registry[ModerationHistory]
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


def test_employer_cannot_see_admin_only_data_on_own_detail(make_employer, make_post, auth_client):
    owner = make_employer()
    post = make_post(employer=owner)
    body = auth_client(owner).get(post_url(post.pk)).json()
    assert "employer_info" not in body and "moderation_history" not in body
    assert timezone.now()


@pytest.mark.parametrize("reason", ["", "  ", "ab", None])
def test_service_itself_refuses_a_rejection_without_reason(make_employer, make_post, staff, reason):
    """Defense in depth: the rule holds even for callers that bypass the API serializer."""
    from rest_framework.exceptions import ValidationError

    from apps.moderation import services

    owner = make_employer()
    post = make_post(employer=owner)
    services.submit_for_review(post, actor=owner)
    with pytest.raises(ValidationError):
        services.reject(post, reviewer=staff, reason=reason)
    post.refresh_from_db()
    assert post.moderation_status == "PENDING_REVIEW"
    assert ModerationHistory.objects.filter(job_post=post, to_status="REJECTED").count() == 0

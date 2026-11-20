"""The moderation state machine. Every change of `moderation_status` goes through here and
leaves a ModerationHistory row, in the same transaction.

DRAFT --submit--> PENDING_REVIEW --approve--> APPROVED
                       |                         |
                       +--reject--> REJECTED     +--(owner edits)--> PENDING_REVIEW
REJECTED --(owner edits)--> DRAFT --submit--> PENDING_REVIEW
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.exceptions import Conflict
from apps.jobs.models import JobPost, LifecycleStatus, ModerationStatus, PostType

from .models import ModerationHistory

MAX_PENDING_PER_EMPLOYER = 10


def _lock(post: JobPost) -> JobPost:
    return JobPost.objects.select_for_update().get(pk=post.pk)


def _record(post, actor, old, new, note=""):
    ModerationHistory.objects.create(
        job_post=post, actor=actor, from_status=old, to_status=new, note=note
    )


def _move(post, actor, new_status, note="", **extra_fields):
    old = post.moderation_status
    post.moderation_status = new_status
    for name, value in extra_fields.items():
        setattr(post, name, value)
    post.save(update_fields=["moderation_status", "updated_at", *extra_fields])
    _record(post, actor, old, new_status, note)


@transaction.atomic
def submit_for_review(post: JobPost, *, actor) -> JobPost:
    post = _lock(post)
    if post.moderation_status not in (ModerationStatus.DRAFT, ModerationStatus.REJECTED):
        raise Conflict("Only a draft or rejected post can be submitted for review.")
    detail = "employment_detail" if post.post_type == PostType.EMPLOYMENT else "project_detail"
    if not hasattr(post, detail):  # defensive: the API always creates the detail with the post
        raise ValidationError({"detail": "The post has no details yet."})
    pending = JobPost.objects.filter(
        employer=post.employer, moderation_status=ModerationStatus.PENDING_REVIEW
    ).count()
    if pending >= MAX_PENDING_PER_EMPLOYER:
        raise ValidationError(
            {"detail": f"You already have {pending} posts waiting for review. Please wait."}
        )
    _move(post, actor, ModerationStatus.PENDING_REVIEW, moderation_note="")
    return post


@transaction.atomic
def approve(post: JobPost, *, reviewer, note: str = "") -> JobPost:
    post = _lock(post)
    if post.moderation_status != ModerationStatus.PENDING_REVIEW:
        raise Conflict("Only a post that is pending review can be approved.")
    now = timezone.now()
    _move(
        post,
        reviewer,
        ModerationStatus.APPROVED,
        note,
        lifecycle_status=LifecycleStatus.ACTIVE,
        published_at=now,
        expires_at=now + timedelta(days=post.duration_days),
        moderation_note=note,
    )
    transaction.on_commit(lambda: _queue_embedding(post.pk))
    return post


def _queue_embedding(post_id: int) -> None:
    """A newly public post gets its text vector prepared in the background (no-op when no AI
    provider is configured). Imported here so moderation does not depend on matching at load."""
    from apps.matching.tasks import embed_post

    embed_post.delay(post_id)


@transaction.atomic
def reject(post: JobPost, *, reviewer, reason: str) -> JobPost:
    post = _lock(post)
    if post.moderation_status != ModerationStatus.PENDING_REVIEW:
        raise Conflict("Only a post that is pending review can be rejected.")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationError({"reason": ["A rejection reason is required."]})
    _move(post, reviewer, ModerationStatus.REJECTED, reason, moderation_note=reason)
    return post


def register_edit(post: JobPost, *, actor) -> None:
    """Call (inside the edit transaction) after an employer changed a post's content.
    Editing approved content sends it back to review so moderation cannot be bypassed."""
    if post.moderation_status == ModerationStatus.APPROVED:
        _move(post, actor, ModerationStatus.PENDING_REVIEW, "Edited after approval")
    elif post.moderation_status == ModerationStatus.REJECTED:
        _move(post, actor, ModerationStatus.DRAFT, "Edited after rejection")

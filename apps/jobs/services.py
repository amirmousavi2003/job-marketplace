from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import Conflict
from apps.common.text import normalize_text
from apps.moderation import services as moderation

from .models import (
    EmploymentDetail,
    JobPost,
    JobPostSkill,
    LifecycleStatus,
    ModerationStatus,
    PostType,
    ProjectDetail,
)

DETAIL_MODELS = {PostType.EMPLOYMENT: EmploymentDetail, PostType.PROJECT: ProjectDetail}
DETAIL_RELATION = {PostType.EMPLOYMENT: "employment_detail", PostType.PROJECT: "project_detail"}


def refresh_search_text(post: JobPost) -> None:
    """Rebuild the normalized text used by keyword search (title, description, names)."""
    post = JobPost.objects.select_related(
        "company", "category", "province", "city", "employer"
    ).get(pk=post.pk)
    parts = [post.title, post.description, post.employer.display_name]
    if post.company:
        parts.append(post.company.name)
    parts += [post.category.name_fa, post.category.name_en]
    parts += [post.province.name if post.province else "", post.city.name if post.city else ""]
    for link in post.post_skills.select_related("skill"):
        parts += [link.skill.name_fa, link.skill.name_en]
    JobPost.objects.filter(pk=post.pk).update(
        title_normalized=normalize_text(post.title),
        search_text=normalize_text(" ".join(p for p in parts if p)),
    )


def _replace_skills(post: JobPost, skills: list[dict]) -> None:
    post.post_skills.all().delete()
    JobPostSkill.objects.bulk_create(
        [
            JobPostSkill(
                job_post=post,
                skill=item["skill"],
                is_required=item.get("is_required", True),
                minimum_level=item.get("minimum_level", ""),
            )
            for item in skills
        ]
    )


@transaction.atomic
def create_job_post(
    *, employer, post_type, data: dict, detail: dict, skills: list[dict]
) -> JobPost:
    """Create the post and its single matching detail record atomically, as a DRAFT."""
    post = JobPost.objects.create(employer=employer, post_type=post_type, **data)
    DETAIL_MODELS[post_type].objects.create(job_post=post, **detail)
    _replace_skills(post, skills)
    refresh_search_text(post)
    return post


@transaction.atomic
def update_job_post(post, *, actor, data: dict, detail: dict | None, skills: list[dict] | None):
    post = JobPost.objects.select_for_update().get(pk=post.pk)
    for field, value in data.items():
        setattr(post, field, value)
    post.save()
    if detail:
        row = getattr(post, DETAIL_RELATION[post.post_type])
        for field, value in detail.items():
            setattr(row, field, value)
        row.save()
    if skills is not None:
        _replace_skills(post, skills)
    refresh_search_text(post)
    moderation.register_edit(post, actor=actor)
    return post


def delete_job_post(post: JobPost) -> None:
    if post.moderation_status not in (ModerationStatus.DRAFT, ModerationStatus.REJECTED):
        raise Conflict("Only drafts and rejected posts can be deleted. Deactivate it instead.")
    post.delete()


@transaction.atomic
def deactivate(post: JobPost) -> JobPost:
    post = JobPost.objects.select_for_update().get(pk=post.pk)
    if post.moderation_status != ModerationStatus.APPROVED:
        raise Conflict("Only an approved post can be deactivated.")
    if post.lifecycle_status != LifecycleStatus.ACTIVE:
        raise Conflict("The post is not active.")
    post.lifecycle_status = LifecycleStatus.DEACTIVATED
    post.save(update_fields=["lifecycle_status", "updated_at"])
    return post


@transaction.atomic
def activate(post: JobPost) -> JobPost:
    post = JobPost.objects.select_for_update().get(pk=post.pk)
    if post.moderation_status != ModerationStatus.APPROVED:
        raise Conflict("Only an approved post can be activated.")
    if post.lifecycle_status != LifecycleStatus.DEACTIVATED:
        raise Conflict("Only a deactivated post can be activated.")
    if post.expires_at is None or post.expires_at <= timezone.now():
        raise Conflict("The post has expired. Renew it instead.")
    post.lifecycle_status = LifecycleStatus.ACTIVE
    post.save(update_fields=["lifecycle_status", "updated_at"])
    return post


@transaction.atomic
def renew(post: JobPost) -> JobPost:
    """Extend an approved post by its duration, from now. No new review is needed."""
    post = JobPost.objects.select_for_update().get(pk=post.pk)
    if post.moderation_status != ModerationStatus.APPROVED:
        raise Conflict("Only an approved post can be renewed.")
    post.lifecycle_status = LifecycleStatus.ACTIVE
    post.expires_at = timezone.now() + timedelta(days=post.duration_days)
    post.save(update_fields=["lifecycle_status", "expires_at", "updated_at"])
    return post


def expire_overdue_posts() -> int:
    """Flip active approved posts past their expiry to EXPIRED. Run periodically.
    (Visibility never depends on this: selectors also check expires_at.)"""
    return JobPost.objects.filter(
        moderation_status=ModerationStatus.APPROVED,
        lifecycle_status=LifecycleStatus.ACTIVE,
        expires_at__lte=timezone.now(),
    ).update(lifecycle_status=LifecycleStatus.EXPIRED, updated_at=timezone.now())

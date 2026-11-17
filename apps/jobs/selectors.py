from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import JobPost, JobPostSkill, LifecycleStatus, ModerationStatus


def visible_q(now=None) -> Q:
    """THE definition of 'publicly visible'. Every public query must use it."""
    now = now or timezone.now()
    return (
        Q(
            moderation_status=ModerationStatus.APPROVED,
            lifecycle_status=LifecycleStatus.ACTIVE,
            expires_at__gt=now,
            employer__user__is_active=True,
        )
    ) & (Q(company__isnull=True) | Q(company__is_active=True))


def is_visible(post: JobPost, now=None) -> bool:
    now = now or timezone.now()
    return bool(
        post.moderation_status == ModerationStatus.APPROVED
        and post.lifecycle_status == LifecycleStatus.ACTIVE
        and post.expires_at
        and post.expires_at > now
        and post.employer.user.is_active
        and (post.company is None or post.company.is_active)
    )


def base_queryset():
    """Posts with everything the serializers need, loaded in a fixed number of queries."""
    return JobPost.objects.select_related(
        "employer",
        "employer__user",
        "company",
        "category",
        "province",
        "city",
        "employment_detail",
        "project_detail",
    ).prefetch_related(Prefetch("post_skills", JobPostSkill.objects.select_related("skill")))


def visible_posts():
    return base_queryset().filter(visible_q())


def owned_posts(employer):
    return base_queryset().filter(employer=employer)


def get_post_for_viewer(pk: int, user):
    """Public if visible; otherwise only its owner can see it. Others get 404."""
    condition = visible_q()
    employer = getattr(user, "employer_profile", None) if user.is_authenticated else None
    if employer is not None:
        condition |= Q(employer=employer)
    return get_object_or_404(base_queryset().filter(condition), pk=pk)

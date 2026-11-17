import django_filters as df
from django.db.models import Case, Count, IntegerField, Q, Value, When
from rest_framework.exceptions import ValidationError

from apps.common.choices import ExperienceLevel, WorkMode
from apps.common.text import normalize_text

from .models import (
    EmploymentType,
    JobPost,
    JobPostSkill,
    LifecycleStatus,
    ModerationStatus,
    PostType,
)

ORDERINGS = {"published_at", "-published_at", "expires_at", "-expires_at"}


def _ids(value: str, field: str) -> list[int]:
    try:
        ids = [int(part) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise ValidationError({field: ["Use a comma-separated list of numeric ids."]}) from exc
    if not ids or len(ids) > 20:
        raise ValidationError({field: ["Provide between 1 and 20 ids."]})
    return ids


class JobPostFilter(df.FilterSet):
    """Public search. All filters combine with AND. Salary/budget filters use range overlap:
    `salary_min=X` keeps posts whose maximum salary is at least X, `salary_max=Y` keeps posts
    whose minimum salary is at most Y. They only match employment (resp. project) posts."""

    q = df.CharFilter(method="filter_q")
    category = df.NumberFilter(method="filter_category")
    type = df.ChoiceFilter(field_name="post_type", choices=PostType.choices)
    province = df.NumberFilter(field_name="province_id")
    city = df.NumberFilter(field_name="city_id")
    work_mode = df.ChoiceFilter(choices=WorkMode.choices)
    employment_type = df.ChoiceFilter(
        field_name="employment_detail__employment_type", choices=EmploymentType.choices
    )
    experience_level = df.ChoiceFilter(
        field_name="employment_detail__required_experience_level", choices=ExperienceLevel.choices
    )
    salary_min = df.NumberFilter(field_name="employment_detail__salary_max", lookup_expr="gte")
    salary_max = df.NumberFilter(field_name="employment_detail__salary_min", lookup_expr="lte")
    budget_min = df.NumberFilter(field_name="project_detail__budget_max", lookup_expr="gte")
    budget_max = df.NumberFilter(field_name="project_detail__budget_min", lookup_expr="lte")
    skills = df.CharFilter(method="filter_skills")
    skills_match = df.ChoiceFilter(
        choices=[("any", "any"), ("all", "all")], method=lambda qs, n, v: qs
    )
    published_after = df.DateFilter(field_name="published_at", lookup_expr="date__gte")
    ordering = df.CharFilter(method="filter_ordering")  # keep last

    class Meta:
        model = JobPost
        fields: list = []

    def filter_q(self, qs, name, value):
        normalized = normalize_text(value)
        tokens = normalized.split()[:8]
        if not tokens:
            return qs
        for token in tokens:
            qs = qs.filter(search_text__contains=token)
        return qs.annotate(
            title_rank=Case(
                When(title_normalized__contains=normalized, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("title_rank", "-published_at", "-id")

    def filter_category(self, qs, name, value):
        return qs.filter(Q(category_id=value) | Q(category__parent_id=value))

    def filter_skills(self, qs, name, value):
        ids = _ids(value, "skills")
        links = JobPostSkill.objects.filter(skill_id__in=ids)
        if self.data.get("skills_match") == "all":
            links = (
                links.values("job_post_id")
                .annotate(matched=Count("skill_id", distinct=True))
                .filter(matched=len(set(ids)))
            )
        return qs.filter(pk__in=links.values("job_post_id"))

    def filter_ordering(self, qs, name, value):
        if value not in ORDERINGS:
            raise ValidationError({"ordering": [f"Use one of: {', '.join(sorted(ORDERINGS))}."]})
        return qs.order_by(value, "-id")


class MyPostFilter(df.FilterSet):
    """Employer's own posts (all states)."""

    type = df.ChoiceFilter(field_name="post_type", choices=PostType.choices)
    moderation_status = df.ChoiceFilter(choices=ModerationStatus.choices)
    lifecycle_status = df.ChoiceFilter(choices=LifecycleStatus.choices)

    class Meta:
        model = JobPost
        fields: list = []

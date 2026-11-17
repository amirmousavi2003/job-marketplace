from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q

from apps.common.choices import DegreeLevel, ExperienceLevel, SkillLevel, WorkMode
from apps.common.models import TimeStampedModel
from apps.companies.models import Company
from apps.locations.models import City, Province
from apps.profiles.models import EmployerProfile
from apps.skills.models import JobCategory, Skill


class PostType(models.TextChoices):
    EMPLOYMENT = "EMPLOYMENT", "Employment"
    PROJECT = "PROJECT", "Freelance project"


class ModerationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class LifecycleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DEACTIVATED = "DEACTIVATED", "Deactivated by employer"
    EXPIRED = "EXPIRED", "Expired"


class JobPost(TimeStampedModel):
    """Shared post. Exactly one detail row (employment OR project) matches `post_type`.

    Two independent state fields:
      moderation_status: where the post is in the admin review workflow.
      lifecycle_status:  operational state of an approved post (active / deactivated / expired).
    A post is public only when APPROVED + ACTIVE + not past expires_at (see selectors.visible_q).
    """

    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.PROTECT, related_name="job_posts"
    )
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name="job_posts"
    )
    post_type = models.CharField(max_length=10, choices=PostType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(JobCategory, on_delete=models.PROTECT, related_name="job_posts")
    province = models.ForeignKey(
        Province, null=True, blank=True, on_delete=models.PROTECT, related_name="job_posts"
    )
    city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.PROTECT, related_name="job_posts"
    )
    work_mode = models.CharField(max_length=10, choices=WorkMode.choices)

    moderation_status = models.CharField(
        max_length=15, choices=ModerationStatus.choices, default=ModerationStatus.DRAFT
    )
    lifecycle_status = models.CharField(
        max_length=12, choices=LifecycleStatus.choices, default=LifecycleStatus.ACTIVE
    )
    moderation_note = models.TextField(
        blank=True, help_text="Last reviewer note (rejection reason)."
    )
    duration_days = models.PositiveSmallIntegerField(default=30)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # derived, for search (rebuilt by services.refresh_search_text)
    title_normalized = models.CharField(max_length=200, blank=True, editable=False)
    search_text = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # Target of the composite foreign keys from the detail tables (see migration 0001).
            models.UniqueConstraint(fields=["id", "post_type"], name="jobs_jobpost_id_type_uniq"),
            models.CheckConstraint(
                condition=Q(duration_days__gte=1) & Q(duration_days__lte=90),
                name="jobs_jobpost_duration_1_90",
            ),
        ]
        indexes = [
            models.Index(
                fields=["moderation_status", "lifecycle_status", "-published_at"],
                name="jobs_post_public_idx",
            ),
            models.Index(fields=["post_type", "category"], name="jobs_post_type_cat_idx"),
            models.Index(fields=["province", "city"], name="jobs_post_location_idx"),
            models.Index(fields=["employer", "moderation_status"], name="jobs_post_employer_idx"),
            GinIndex(
                fields=["search_text"], name="jobs_post_search_trgm", opclasses=["gin_trgm_ops"]
            ),
        ]

    def __str__(self):
        return f"[{self.post_type}] {self.title}"


class EmploymentType(models.TextChoices):
    FULL_TIME = "FULL_TIME", "Full-time"
    PART_TIME = "PART_TIME", "Part-time"
    CONTRACT = "CONTRACT", "Contract"
    INTERNSHIP = "INTERNSHIP", "Internship"
    TEMPORARY = "TEMPORARY", "Temporary"


class EmploymentDetail(TimeStampedModel):
    job_post = models.OneToOneField(
        JobPost, on_delete=models.CASCADE, related_name="employment_detail"
    )
    # Redundant on purpose: with the composite FK (job_post_id, post_type) the database itself
    # guarantees this row can only attach to a post whose type is EMPLOYMENT.
    post_type = models.CharField(max_length=10, default=PostType.EMPLOYMENT, editable=False)
    employment_type = models.CharField(max_length=12, choices=EmploymentType.choices)
    salary_min = models.PositiveBigIntegerField(help_text="Rial per month")
    salary_max = models.PositiveBigIntegerField(help_text="Rial per month")
    required_experience_level = models.CharField(
        max_length=20, choices=ExperienceLevel.choices, blank=True
    )
    required_education = models.CharField(max_length=20, choices=DegreeLevel.choices, blank=True)
    additional_qualifications = models.TextField(blank=True)
    other_conditions = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(post_type="EMPLOYMENT"), name="jobs_employment_post_type"
            ),
            models.CheckConstraint(
                condition=Q(salary_min__gt=0), name="jobs_employment_salary_min_pos"
            ),
            models.CheckConstraint(
                condition=Q(salary_max__gte=F("salary_min")), name="jobs_employment_salary_range"
            ),
        ]


class Currency(models.TextChoices):
    IRR = "IRR", "Rial"
    USD = "USD", "US dollar"


class ProjectDetail(TimeStampedModel):
    job_post = models.OneToOneField(
        JobPost, on_delete=models.CASCADE, related_name="project_detail"
    )
    post_type = models.CharField(max_length=10, default=PostType.PROJECT, editable=False)
    budget_min = models.PositiveBigIntegerField()
    budget_max = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.IRR)
    expected_duration_days = models.PositiveIntegerField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    expected_deliverables = models.TextField(blank=True)
    additional_requirements = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(post_type="PROJECT"), name="jobs_project_post_type"),
            models.CheckConstraint(
                condition=Q(budget_min__gt=0), name="jobs_project_budget_min_pos"
            ),
            models.CheckConstraint(
                condition=Q(budget_max__gte=F("budget_min")), name="jobs_project_budget_range"
            ),
            models.CheckConstraint(
                condition=Q(expected_duration_days__isnull=True) | Q(expected_duration_days__gt=0),
                name="jobs_project_duration_pos",
            ),
        ]


class JobPostSkill(TimeStampedModel):
    job_post = models.ForeignKey(JobPost, on_delete=models.CASCADE, related_name="post_skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="+")
    is_required = models.BooleanField(default=True)
    minimum_level = models.CharField(max_length=15, choices=SkillLevel.choices, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["job_post", "skill"], name="jobs_unique_post_skill")
        ]

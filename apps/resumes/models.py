from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q

from apps.common.choices import DegreeLevel, ExperienceLevel, SkillLevel, WorkMode
from apps.common.models import TimeStampedModel
from apps.common.text import normalize_text
from apps.common.validators import http_url_validator
from apps.locations.models import City, Province
from apps.profiles.models import JobSeekerProfile
from apps.skills.models import JobTitle, Skill


class EmploymentStatus(models.TextChoices):
    EMPLOYED = "EMPLOYED", "Employed"
    UNEMPLOYED = "UNEMPLOYED", "Unemployed"
    STUDENT = "STUDENT", "Student"
    SELF_EMPLOYED = "SELF_EMPLOYED", "Self-employed / freelancer"


def resume_photo_path(instance, filename):
    # Real name is set by the image processor (random); this is only a safe fallback.
    return f"resume_photos/{filename}"


class Resume(TimeStampedModel):
    """The single main resume of a job seeker. First/last name live on JobSeekerProfile."""

    job_seeker = models.OneToOneField(
        JobSeekerProfile, on_delete=models.CASCADE, related_name="resume"
    )
    # personal / contact
    province = models.ForeignKey(Province, null=True, blank=True, on_delete=models.PROTECT)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.PROTECT)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to=resume_photo_path, null=True, blank=True)
    introduction = models.TextField(blank=True)
    # employment preferences
    experience_level = models.CharField(max_length=20, choices=ExperienceLevel.choices, blank=True)
    employment_status = models.CharField(
        max_length=20, choices=EmploymentStatus.choices, blank=True
    )
    desired_work_modes = ArrayField(
        models.CharField(max_length=10, choices=WorkMode.choices), default=list, blank=True
    )
    expected_monthly_salary = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Rial per month. Optional; used by AI matching."
    )
    has_no_work_experience = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(expected_monthly_salary__isnull=True)
                | Q(expected_monthly_salary__gt=0),
                name="resumes_resume_salary_positive",
            ),
        ]

    def __str__(self):
        return f"Resume of {self.job_seeker}"


class Education(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="educations")
    degree = models.CharField(max_length=20, choices=DegreeLevel.choices)
    field_of_study = models.CharField(max_length=150)
    institution = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Empty means still studying.")

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="resumes_education_dates_ordered",
            )
        ]


class WorkExperience(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="work_experiences")
    job_title = models.CharField(max_length=150)
    company_name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Empty means current job.")
    description = models.TextField(blank=True)
    responsibilities = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="resumes_workexperience_dates_ordered",
            )
        ]


class ResumeSkill(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="resume_skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="+")
    level = models.CharField(max_length=15, choices=SkillLevel.choices)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["resume", "skill"], name="resumes_unique_skill")
        ]


class DesiredJobTitle(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="desired_job_titles")
    job_title = models.ForeignKey(JobTitle, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["resume", "job_title"], name="resumes_unique_title")
        ]


class LanguageLevel(models.TextChoices):
    BASIC = "BASIC", "Basic"
    CONVERSATIONAL = "CONVERSATIONAL", "Conversational"
    FLUENT = "FLUENT", "Fluent"
    NATIVE = "NATIVE", "Native"


class Language(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="languages")
    name = models.CharField(max_length=60)
    normalized_name = models.CharField(max_length=60, editable=False)
    proficiency = models.CharField(max_length=15, choices=LanguageLevel.choices)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["resume", "normalized_name"], name="resumes_unique_language"
            )
        ]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_text(self.name)
        super().save(*args, **kwargs)


class Certificate(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="certificates")
    title = models.CharField(max_length=150)
    issuer = models.CharField(max_length=150, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    credential_url = models.URLField(max_length=500, blank=True, validators=[http_url_validator])

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expiry_date__isnull=True)
                | Q(issue_date__isnull=True)
                | Q(expiry_date__gte=F("issue_date")),
                name="resumes_certificate_dates_ordered",
            )
        ]


class PortfolioItem(TimeStampedModel):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="portfolio_items")
    title = models.CharField(max_length=150)
    url = models.URLField(max_length=500, validators=[http_url_validator])
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

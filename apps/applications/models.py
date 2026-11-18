"""Employment applications and freelance project proposals: two separate business processes.

Both link to a JobPost of the matching type. As for the detail tables in `jobs`, a redundant
`post_type` column plus a composite foreign key (see migration) lets the database itself refuse
an application on a project post or a proposal on an employment post.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.jobs.models import JobPost, PostType
from apps.profiles.models import JobSeekerProfile
from apps.resumes.models import Resume


class ApplicationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    REVIEWING = "REVIEWING", "Reviewing"
    INTERVIEW = "INTERVIEW", "Interview"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn by applicant"


class ProposalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    REVIEWING = "REVIEWING", "Reviewing"
    NEGOTIATING = "NEGOTIATING", "Negotiating"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Application(TimeStampedModel):
    job_seeker = models.ForeignKey(
        JobSeekerProfile, on_delete=models.PROTECT, related_name="applications"
    )
    job_post = models.ForeignKey(JobPost, on_delete=models.PROTECT, related_name="applications")
    post_type = models.CharField(max_length=10, default=PostType.EMPLOYMENT, editable=False)
    # Live resume is only a reference. What the employer reviews is `resume_snapshot`, frozen
    # at submission, so later resume edits cannot silently change an application.
    resume = models.ForeignKey(Resume, null=True, on_delete=models.SET_NULL, related_name="+")
    resume_snapshot = models.JSONField()
    snapshot_version = models.PositiveSmallIntegerField(default=1)
    cover_letter = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(post_type="EMPLOYMENT"), name="applications_application_post_type"
            ),
            # One application per seeker and post. Only a withdrawn one can be replaced.
            models.UniqueConstraint(
                fields=["job_seeker", "job_post"],
                condition=~Q(status="WITHDRAWN"),
                name="applications_one_per_seeker_post",
            ),
        ]
        indexes = [
            models.Index(fields=["job_post", "status"], name="applications_post_status_idx"),
            models.Index(fields=["job_seeker", "status"], name="applications_seeker_idx"),
        ]

    def __str__(self):
        return f"Application {self.pk} ({self.status})"


class ProjectProposal(TimeStampedModel):
    job_seeker = models.ForeignKey(
        JobSeekerProfile, on_delete=models.PROTECT, related_name="project_proposals"
    )
    job_post = models.ForeignKey(JobPost, on_delete=models.PROTECT, related_name="proposals")
    post_type = models.CharField(max_length=10, default=PostType.PROJECT, editable=False)
    proposed_price = models.PositiveBigIntegerField(help_text="In the project's currency")
    estimated_days = models.PositiveIntegerField()
    description = models.TextField()
    status = models.CharField(
        max_length=12, choices=ProposalStatus.choices, default=ProposalStatus.PENDING
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(post_type="PROJECT"), name="applications_proposal_post_type"
            ),
            models.CheckConstraint(
                condition=Q(proposed_price__gt=0), name="applications_proposal_price_positive"
            ),
            models.CheckConstraint(
                condition=Q(estimated_days__gt=0), name="applications_proposal_days_positive"
            ),
            models.UniqueConstraint(
                fields=["job_seeker", "job_post"],
                condition=~Q(status="WITHDRAWN"),
                name="applications_one_proposal_per_seeker_post",
            ),
        ]
        indexes = [
            models.Index(fields=["job_post", "status"], name="proposals_post_status_idx"),
            models.Index(fields=["job_seeker", "status"], name="proposals_seeker_idx"),
        ]

    def __str__(self):
        return f"Proposal {self.pk} ({self.status})"


class StatusHistory(models.Model):
    """Append-only record of one status change. The first row (from_status empty) is submission."""

    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["id"]


class ApplicationStatusHistory(StatusHistory):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="history")

    class Meta(StatusHistory.Meta):
        verbose_name_plural = "application status history"

    def __str__(self):
        return f"Application {self.application_id}: {self.from_status or '-'} -> {self.to_status}"


class ProjectProposalStatusHistory(StatusHistory):
    proposal = models.ForeignKey(ProjectProposal, on_delete=models.CASCADE, related_name="history")

    class Meta(StatusHistory.Meta):
        verbose_name_plural = "project proposal status history"

    def __str__(self):
        return f"Proposal {self.proposal_id}: {self.from_status or '-'} -> {self.to_status}"

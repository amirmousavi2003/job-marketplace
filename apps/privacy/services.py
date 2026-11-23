"""Account erasure: remove personal data, keep what other people's records depend on.

Deactivation (accounts) is a reversible pause. Erasure is final: the person is anonymized and can
never log in again, while employers keep an intact (anonymous) history of what happened.

Removed: resume with all sections and photo, stored AI matches, the frozen resume copies and cover
letters in applications, proposal texts, name, email, phone, password, company membership.
Kept (without personal data): application / proposal rows and their status history, job posts
(hidden), moderation history, catalogue suggestions (unlinked from the person)."""

from django.db import transaction
from django.utils import timezone

from apps.accounts.services import blacklist_all_tokens
from apps.applications import services as application_services
from apps.applications.models import Application, ApplicationStatus, ProjectProposal, ProposalStatus
from apps.common.exceptions import Conflict
from apps.companies.models import CompanyMembership
from apps.jobs.models import JobPost, LifecycleStatus
from apps.matching.models import AIMatch
from apps.resumes import services as resume_services
from apps.resumes.models import Resume
from apps.skills.models import JobTitleSuggestion, SkillSuggestion

ERASED_NAME = ("کاربر", "حذف‌شده")
ERASED_TEXT = "[حذف‌شده]"


def _erase_employer(employer) -> None:
    memberships = list(
        CompanyMembership.objects.filter(employer=employer).select_related("company")
    )
    for membership in memberships:
        if membership.role != CompanyMembership.Role.OWNER:
            continue
        if (
            CompanyMembership.objects.filter(company=membership.company)
            .exclude(pk=membership.pk)
            .exists()
        ):
            raise Conflict(
                f"You own the company '{membership.company.name}' and it has other members. "
                "Remove them first (or ask them to leave)."
            )
    for membership in memberships:
        if (
            membership.role == CompanyMembership.Role.OWNER
        ):  # the only member: the company ends with them
            membership.company.is_active = False
            membership.company.save(update_fields=["is_active", "updated_at"])
    CompanyMembership.objects.filter(employer=employer).delete()
    JobPost.objects.filter(employer=employer).update(
        lifecycle_status=LifecycleStatus.DEACTIVATED, updated_at=timezone.now()
    )
    employer.display_name = "حساب حذف‌شده"
    employer.about = ""
    employer.save(update_fields=["display_name", "about", "updated_at"])


def _withdraw_open_submissions(profile, user) -> None:
    """Tell employers the applicant is gone: open items become WITHDRAWN (with history)."""
    for application in Application.objects.filter(job_seeker=profile):
        if (
            application.status
            in application_services.APPLICATION.rules[application_services.APPLICANT]
        ):
            application_services.change_status(
                application_services.APPLICATION,
                application,
                actor=user,
                role=application_services.APPLICANT,
                to_status=ApplicationStatus.WITHDRAWN,
                note="Account erased",
            )
    for proposal in ProjectProposal.objects.filter(job_seeker=profile):
        if proposal.status in application_services.PROPOSAL.rules[application_services.APPLICANT]:
            application_services.change_status(
                application_services.PROPOSAL,
                proposal,
                actor=user,
                role=application_services.APPLICANT,
                to_status=ProposalStatus.WITHDRAWN,
                note="Account erased",
            )


def _erase_job_seeker(profile, user) -> None:
    _withdraw_open_submissions(profile, user)
    Application.objects.filter(job_seeker=profile).update(
        resume_snapshot={"erased": True, "version": 1}, cover_letter="", resume=None
    )
    ProjectProposal.objects.filter(job_seeker=profile).update(description=ERASED_TEXT)
    AIMatch.objects.filter(job_seeker=profile).delete()
    resume = Resume.objects.filter(job_seeker=profile).first()
    if resume:
        resume_services.remove_photo(resume)  # deletes the file from storage too
        resume.delete()  # education, experience, skills, languages, ... cascade
    profile.first_name, profile.last_name = ERASED_NAME
    profile.save(update_fields=["first_name", "last_name", "updated_at"])


@transaction.atomic
def erase_account(user) -> None:
    if user.is_staff or user.is_superuser:
        raise Conflict("Staff accounts cannot be erased here. Remove the staff status first.")
    employer = getattr(user, "employer_profile", None)
    profile = getattr(user, "job_seeker_profile", None)
    if employer is not None:
        _erase_employer(employer)
    if profile is not None:
        _erase_job_seeker(profile, user)
    SkillSuggestion.objects.filter(suggested_by=user).update(suggested_by=None)
    JobTitleSuggestion.objects.filter(suggested_by=user).update(suggested_by=None)

    user.email = f"erased-{user.pk}@erased.invalid"  # frees the real address for a new sign-up
    user.phone = None
    user.is_active = False
    user.set_unusable_password()
    user.save()
    blacklist_all_tokens(user)

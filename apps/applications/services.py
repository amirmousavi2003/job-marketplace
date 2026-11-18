"""Submitting applications / proposals and moving them through their status machines.

Every status change writes a history row in the same transaction. Who may do what is decided
here (not in views), so any caller gets the same rules."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.common.exceptions import Conflict
from apps.jobs.models import PostType
from apps.jobs.selectors import visible_posts
from apps.resumes import services as resume_services
from apps.resumes.selectors import resume_queryset

from .models import (
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
    ProjectProposal,
    ProjectProposalStatusHistory,
    ProposalStatus,
)
from .snapshot import SNAPSHOT_VERSION, build_resume_snapshot

EMPLOYER, APPLICANT = "employer", "applicant"


@dataclass(frozen=True)
class Machine:
    """Allowed status changes per role: {role: {current_status: {next_statuses}}}."""

    model: type
    history_model: type
    history_fk: str
    rules: dict

    def targets(self, role: str) -> set:
        return set().union(*self.rules[role].values())

    def allowed_next(self, role: str, status: str) -> list[str]:
        return sorted(self.rules[role].get(status, set()))


_S, _P = ApplicationStatus, ProposalStatus

APPLICATION = Machine(
    Application,
    ApplicationStatusHistory,
    "application",
    {
        EMPLOYER: {
            _S.PENDING: {_S.REVIEWING, _S.REJECTED},
            _S.REVIEWING: {_S.INTERVIEW, _S.REJECTED},
            _S.INTERVIEW: {_S.ACCEPTED, _S.REJECTED},
        },
        APPLICANT: {
            _S.PENDING: {_S.WITHDRAWN},
            _S.REVIEWING: {_S.WITHDRAWN},
            _S.INTERVIEW: {_S.WITHDRAWN},
        },
    },
)
PROPOSAL = Machine(
    ProjectProposal,
    ProjectProposalStatusHistory,
    "proposal",
    {
        EMPLOYER: {
            _P.PENDING: {_P.REVIEWING, _P.REJECTED},
            _P.REVIEWING: {_P.NEGOTIATING, _P.ACCEPTED, _P.REJECTED},
            _P.NEGOTIATING: {_P.ACCEPTED, _P.REJECTED},
        },
        APPLICANT: {
            _P.PENDING: {_P.WITHDRAWN},
            _P.REVIEWING: {_P.WITHDRAWN},
            _P.NEGOTIATING: {_P.WITHDRAWN},
        },
    },
)


def _log(machine: Machine, obj, actor, old: str, new: str, note: str = ""):
    machine.history_model.objects.create(
        **{machine.history_fk: obj}, actor=actor, from_status=old, to_status=new, note=note
    )


def _visible_post_of_type(post_id: int, post_type: str, user, wrong_type_message: str):
    """404 unless the post is public (do not reveal hidden posts), then type and ownership rules."""
    post = get_object_or_404(visible_posts(), pk=post_id)
    if post.post_type != post_type:
        raise ValidationError({"detail": wrong_type_message})
    if post.employer.user_id == user.pk:
        raise ValidationError({"detail": "You cannot apply to your own post."})
    return post


@transaction.atomic
def submit_application(*, user, post_id: int, cover_letter: str = "") -> Application:
    post = _visible_post_of_type(
        post_id,
        PostType.EMPLOYMENT,
        user,
        "Job applications are only for employment posts. Use a project proposal instead.",
    )
    profile = user.job_seeker_profile
    resume = resume_queryset().filter(job_seeker=profile).first()
    if resume is None:
        raise ValidationError({"resume": ["Create your resume before applying."]})
    state = resume_services.completeness(resume)
    if not state["is_complete"]:
        raise ValidationError(
            {"resume": ["Complete your resume before applying."], "missing": state["missing"]}
        )
    if (
        Application.objects.filter(job_seeker=profile, job_post=post)
        .exclude(status=ApplicationStatus.WITHDRAWN)
        .exists()
    ):
        raise Conflict("You have already applied to this post.")
    try:
        with transaction.atomic():
            application = Application.objects.create(
                job_seeker=profile,
                job_post=post,
                resume=resume,
                resume_snapshot=build_resume_snapshot(resume),
                snapshot_version=SNAPSHOT_VERSION,
                cover_letter=cover_letter,
            )
    except IntegrityError as exc:  # concurrent double submit
        raise Conflict("You have already applied to this post.") from exc
    _log(APPLICATION, application, user, "", ApplicationStatus.PENDING)
    return application


@transaction.atomic
def submit_proposal(
    *, user, post_id: int, proposed_price: int, estimated_days: int, description: str
) -> ProjectProposal:
    post = _visible_post_of_type(
        post_id,
        PostType.PROJECT,
        user,
        "Project proposals are only for freelance projects. Use a job application instead.",
    )
    profile = user.job_seeker_profile
    if (
        ProjectProposal.objects.filter(job_seeker=profile, job_post=post)
        .exclude(status=ProposalStatus.WITHDRAWN)
        .exists()
    ):
        raise Conflict("You have already sent a proposal for this project.")
    try:
        with transaction.atomic():
            proposal = ProjectProposal.objects.create(
                job_seeker=profile,
                job_post=post,
                proposed_price=proposed_price,
                estimated_days=estimated_days,
                description=description,
            )
    except IntegrityError as exc:
        raise Conflict("You have already sent a proposal for this project.") from exc
    _log(PROPOSAL, proposal, user, "", ProposalStatus.PENDING)
    return proposal


@transaction.atomic
def change_status(machine: Machine, obj, *, actor, role: str, to_status: str, note: str = ""):
    """403 if this role may never set that status, 409 if not allowed from the current one."""
    if to_status not in machine.targets(role):
        raise PermissionDenied(f"You cannot set the status to {to_status}.")
    locked = machine.model.objects.select_for_update().get(pk=obj.pk)
    if to_status not in machine.rules[role].get(locked.status, set()):
        allowed = machine.allowed_next(role, locked.status) or "none (final state)"
        raise Conflict(
            f"Cannot change status from {locked.status} to {to_status}. Allowed: {allowed}."
        )
    old = locked.status
    locked.status = to_status
    locked.save(update_fields=["status", "updated_at"])
    _log(machine, locked, actor, old, to_status, note)
    return locked

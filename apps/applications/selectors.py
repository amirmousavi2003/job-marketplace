from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import Application, ProjectProposal
from .services import APPLICANT, EMPLOYER


def application_queryset():
    return Application.objects.select_related("job_seeker__user", "job_post__company")


def proposal_queryset():
    return ProjectProposal.objects.select_related(
        "job_seeker__user", "job_seeker__resume", "job_post__company", "job_post__project_detail"
    )


def get_for_party(queryset, pk: int, user):
    """The applicant or the owner of the post can open it; everyone else gets 404.
    Returns (object, role)."""
    condition = Q(job_seeker__user=user)
    employer = getattr(user, "employer_profile", None)
    if employer is not None:
        condition |= Q(job_post__employer=employer)
    obj = get_object_or_404(queryset.filter(condition), pk=pk)
    return obj, (APPLICANT if obj.job_seeker.user_id == user.pk else EMPLOYER)

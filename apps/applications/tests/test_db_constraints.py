import pytest
from django.db import IntegrityError, connection, transaction

from apps.applications.models import Application, ProjectProposal
from apps.jobs.models import PostType

pytestmark = pytest.mark.django_db


def make_raw_application(post, seeker, **kw):
    return Application.objects.create(
        job_seeker=seeker.job_seeker_profile, job_post=post, resume_snapshot={}, **kw
    )


def make_raw_proposal(post, seeker, **kw):
    fields = {"proposed_price": 5, "estimated_days": 3, "description": "d", **kw}
    return ProjectProposal.objects.create(
        job_seeker=seeker.job_seeker_profile, job_post=post, **fields
    )


def test_application_cannot_attach_to_a_project_post(project, make_seeker):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_application(project, make_seeker())


def test_proposal_cannot_attach_to_an_employment_post(job, make_seeker):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_proposal(job, make_seeker())


def test_rows_cannot_lie_about_their_post_type(job, project, make_seeker):
    seeker = make_seeker()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_application(job, seeker, post_type=PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_proposal(project, seeker, post_type=PostType.EMPLOYMENT)


def test_post_type_of_a_post_with_applications_cannot_change(job, make_seeker):
    make_raw_application(job, make_seeker())
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cur:
        cur.execute("UPDATE jobs_jobpost SET post_type='PROJECT' WHERE id=%s", [job.pk])


def test_one_non_withdrawn_application_per_seeker_and_post(job, make_seeker):
    seeker = make_seeker()
    first = make_raw_application(job, seeker)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_application(job, seeker)
    Application.objects.filter(pk=first.pk).update(status="WITHDRAWN")
    current = make_raw_application(job, seeker)  # replacing a withdrawn one is fine
    for status in ("PENDING", "REVIEWING", "INTERVIEW", "ACCEPTED", "REJECTED"):
        Application.objects.filter(pk=current.pk).update(status=status)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_raw_application(job, seeker)


def test_one_non_withdrawn_proposal_per_seeker_and_post(project, make_seeker):
    seeker = make_seeker()
    first = make_raw_proposal(project, seeker)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_proposal(project, seeker)
    ProjectProposal.objects.filter(pk=first.pk).update(status="WITHDRAWN")
    make_raw_proposal(project, seeker)


@pytest.mark.parametrize("bad", [{"proposed_price": 0}, {"estimated_days": 0}])
def test_proposal_numbers_must_be_positive(bad, project, make_seeker):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_raw_proposal(project, make_seeker(), **bad)


def test_posts_and_seekers_with_submissions_are_protected_from_deletion(job, project, make_seeker):
    from django.db.models import ProtectedError

    seeker = make_seeker()
    make_raw_application(job, seeker)
    make_raw_proposal(project, seeker)
    with pytest.raises(ProtectedError):
        job.delete()
    with pytest.raises(ProtectedError):
        project.delete()
    with pytest.raises(ProtectedError):
        seeker.job_seeker_profile.delete()

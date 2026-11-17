import pytest
from django.db import IntegrityError, connection, transaction

from apps.jobs.models import EmploymentDetail, JobPost, JobPostSkill, PostType, ProjectDetail

pytestmark = pytest.mark.django_db

EMP = {"employment_type": "FULL_TIME", "salary_min": 1, "salary_max": 2}
PRJ = {"budget_min": 1, "budget_max": 2}


def raw_post(employer, category, post_type, **kw):
    return JobPost.objects.create(
        employer=employer.employer_profile,
        post_type=post_type,
        title="x" * 6,
        description="y" * 30,
        category=category,
        work_mode="REMOTE",
        **kw,
    )


def test_employment_detail_cannot_attach_to_project_post(make_employer, category):
    post = raw_post(make_employer(), category, PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmploymentDetail.objects.create(job_post=post, **EMP)


def test_project_detail_cannot_attach_to_employment_post(make_employer, category):
    post = raw_post(make_employer(), category, PostType.EMPLOYMENT)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectDetail.objects.create(job_post=post, **PRJ)


def test_detail_row_cannot_lie_about_its_type(make_employer, category):
    post = raw_post(make_employer(), category, PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmploymentDetail.objects.create(job_post=post, post_type="PROJECT", **EMP)


def test_post_type_cannot_change_while_a_detail_exists(make_post):
    post = make_post(post_type=PostType.EMPLOYMENT)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobPost.objects.filter(pk=post.pk).update(post_type=PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cur:
        cur.execute("UPDATE jobs_jobpost SET post_type='PROJECT' WHERE id=%s", [post.pk])


def test_only_one_detail_per_post(make_post):
    post = make_post(post_type=PostType.EMPLOYMENT)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmploymentDetail.objects.create(job_post=post, **EMP)


@pytest.mark.parametrize(
    "bad",
    [
        {"salary_min": 0, "salary_max": 5},
        {"salary_min": 10, "salary_max": 5},
    ],
)
def test_salary_constraints(make_employer, category, bad):
    post = raw_post(make_employer(), category, PostType.EMPLOYMENT)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmploymentDetail.objects.create(job_post=post, employment_type="FULL_TIME", **bad)


@pytest.mark.parametrize(
    "bad",
    [
        {"budget_min": 0, "budget_max": 5},
        {"budget_min": 10, "budget_max": 5},
        {"budget_min": 1, "budget_max": 5, "expected_duration_days": 0},
    ],
)
def test_budget_constraints(make_employer, category, bad):
    post = raw_post(make_employer(), category, PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectDetail.objects.create(job_post=post, **bad)


def test_negative_numbers_are_impossible(make_employer, category):
    post = raw_post(make_employer(), category, PostType.PROJECT)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectDetail.objects.create(job_post=post, budget_min=-5, budget_max=5)


@pytest.mark.parametrize("days", [0, 91, 365])
def test_duration_must_be_1_to_90(make_employer, category, days):
    with pytest.raises(IntegrityError), transaction.atomic():
        raw_post(make_employer(), category, PostType.EMPLOYMENT, duration_days=days)


def test_unique_skill_per_post(make_post, make_skill):
    skill = make_skill("Django")
    post = make_post(skills=[skill])
    with pytest.raises(IntegrityError), transaction.atomic():
        JobPostSkill.objects.create(job_post=post, skill=skill)


def test_employer_with_posts_cannot_be_deleted(make_post):
    post = make_post()
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        post.employer.delete()

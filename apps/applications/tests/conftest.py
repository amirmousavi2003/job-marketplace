import datetime
import itertools

import pytest
from django.utils import timezone

from apps.applications import services
from apps.jobs.models import JobPost, PostType
from apps.jobs.tests.conftest import category, make_post, payloads, shiraz, staff  # noqa: F401
from apps.moderation import services as moderation
from apps.resumes.models import (
    Certificate,
    DesiredJobTitle,
    Education,
    Language,
    PortfolioItem,
    Resume,
    ResumeSkill,
    WorkExperience,
)

PROPOSAL_BODY = {
    "proposed_price": 8_000_000,
    "estimated_days": 10,
    "description": "من این پروژه را در ده روز با کیفیت بالا تحویل می‌دهم.",
}


@pytest.fixture
def make_applicant(make_seeker, make_skill, make_title, shiraz):
    counter = itertools.count(1)

    def _make(first_name="سارا", last_name="احمدی", complete=True, **user_extra):
        user = make_seeker(first_name=first_name, last_name=last_name, **user_extra)
        resume = Resume.objects.create(
            job_seeker=user.job_seeker_profile,
            city=shiraz,
            province=shiraz.province,
            introduction="مسلط به جنگو",
            experience_level="MID",
            employment_status="UNEMPLOYED",
            desired_work_modes=["REMOTE"],
            expected_monthly_salary=30_000_000,
            date_of_birth=datetime.date(1998, 1, 1),
        )
        if complete:
            n = next(counter)
            ResumeSkill.objects.create(
                resume=resume, skill=make_skill(f"Skill {n}", f"مهارت {n}"), level="ADVANCED"
            )
            DesiredJobTitle.objects.create(
                resume=resume, job_title=make_title(f"Title {n}", f"عنوان {n}")
            )
            WorkExperience.objects.create(
                resume=resume,
                job_title="Dev",
                company_name="Acme",
                start_date=datetime.date(2020, 1, 1),
            )
            Education.objects.create(
                resume=resume,
                degree="BACHELOR",
                field_of_study="CE",
                institution="Shiraz Univ",
                start_date=datetime.date(2016, 9, 1),
                end_date=datetime.date(2020, 6, 1),
            )
            Language.objects.create(resume=resume, name="انگلیسی", proficiency="FLUENT")
            Certificate.objects.create(resume=resume, title="ICDL", issuer="TVTO")
            PortfolioItem.objects.create(resume=resume, title="Site", url="https://example.com")
        return user

    return _make


@pytest.fixture
def job(make_post):
    return make_post(published=True)


@pytest.fixture
def project(make_post):
    return make_post(post_type=PostType.PROJECT, published=True)


@pytest.fixture
def make_application(job):
    def _make(applicant, post=None, cover_letter=""):
        return services.submit_application(
            user=applicant, post_id=(post or job).pk, cover_letter=cover_letter
        )

    return _make


@pytest.fixture
def make_proposal(project):
    def _make(applicant, post=None, **overrides):
        return services.submit_proposal(
            user=applicant, post_id=(post or project).pk, **{**PROPOSAL_BODY, **overrides}
        )

    return _make


@pytest.fixture
def hidden_posts(make_post, make_employer, staff):
    """Posts that must never accept applications because the public cannot see them."""
    owner = make_employer()
    draft = make_post(employer=owner)
    pending = make_post(employer=owner)
    moderation.submit_for_review(pending, actor=owner)
    deactivated = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=deactivated.pk).update(lifecycle_status="DEACTIVATED")
    expired = make_post(employer=owner, published=True)
    JobPost.objects.filter(pk=expired.pk).update(
        expires_at=timezone.now() - datetime.timedelta(hours=1)
    )
    return {"draft": draft, "pending": pending, "deactivated": deactivated, "expired": expired}

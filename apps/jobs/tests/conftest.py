import pytest

from apps.jobs import services
from apps.jobs.models import PostType
from apps.locations.models import City
from apps.moderation import services as moderation
from apps.skills.models import JobCategory


@pytest.fixture
def category(db):
    return JobCategory.objects.get(slug="it")


@pytest.fixture
def staff(make_user):
    return make_user(is_staff=True)


@pytest.fixture
def shiraz(db):
    return City.objects.select_related("province").get(name="شیراز")


def employment_payload(cat, /, **overrides):
    payload = {
        "title": "برنامه‌نویس جنگو",
        "description": "به یک برنامه‌نویس مسلط به جنگو و پستگرس نیازمندیم.",
        "category": cat.pk,
        "work_mode": "REMOTE",
        "employment": {
            "employment_type": "FULL_TIME",
            "salary_min": 20_000_000,
            "salary_max": 40_000_000,
        },
    }
    payload.update(overrides)
    return payload


def project_payload(cat, /, **overrides):
    payload = {
        "title": "طراحی لوگو برای فروشگاه",
        "description": "طراحی یک لوگوی مدرن به همراه راهنمای برند و فایل‌های نهایی.",
        "category": cat.pk,
        "work_mode": "REMOTE",
        "project": {"budget_min": 5_000_000, "budget_max": 10_000_000, "currency": "IRR"},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def payloads(category):
    class P:
        employment = staticmethod(lambda **kw: employment_payload(category, **kw))
        project = staticmethod(lambda **kw: project_payload(category, **kw))

    return P


@pytest.fixture
def make_post(make_employer, category, staff):
    """Create a post through the real service. published=True also runs submit + approve."""
    counter = iter(range(1, 10_000))

    def _make(
        employer=None,
        post_type=PostType.EMPLOYMENT,
        published=False,
        title=None,
        description="شرح کامل و طولانی آگهی برای آزمون جستجو و فیلتر.",
        work_mode="REMOTE",
        detail=None,
        skills=(),
        duration_days=30,
        **fields,
    ):
        employer = employer or make_employer()
        if detail is None:
            detail = (
                {"employment_type": "FULL_TIME", "salary_min": 10_000_000, "salary_max": 20_000_000}
                if post_type == PostType.EMPLOYMENT
                else {"budget_min": 1_000_000, "budget_max": 5_000_000, "currency": "IRR"}
            )
        data = {
            "title": title or f"آگهی شماره {next(counter)}",
            "description": description,
            "category": fields.pop("category", category),
            "work_mode": work_mode,
            "duration_days": duration_days,
            **fields,
        }
        post = services.create_job_post(
            employer=employer.employer_profile,
            post_type=post_type,
            data=data,
            detail=detail,
            skills=[{"skill": s, "is_required": True, "minimum_level": ""} for s in skills],
        )
        if published:
            moderation.submit_for_review(post, actor=employer)
            moderation.approve(post, reviewer=staff)
            post.refresh_from_db()
        return post

    return _make

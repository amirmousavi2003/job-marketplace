import pytest
from django.core.cache import cache

from apps.applications.tests.conftest import (  # noqa: F401
    category,
    hidden_posts,
    job,
    make_applicant,
    make_application,
    make_post,
    make_proposal,
    payloads,
    project,
    shiraz,
    staff,
)
from apps.matching.providers import EmbeddingError, EmbeddingProvider
from apps.matching.providers.local_ngram import LocalNgramProvider
from apps.resumes.models import DesiredJobTitle, Resume, ResumeSkill


@pytest.fixture(autouse=True)
def _clean_state(settings):
    cache.clear()
    settings.AI_EMBEDDING_PROVIDER = "local_ngram"
    yield
    cache.clear()


class FakeNeuralProvider(EmbeddingProvider):
    """Stands in for a network provider in tests only. Deterministic dense vectors."""

    name = "fake_neural"
    model = "fake-1"
    kind = "neural"
    inline_ok = False

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self._impl = LocalNgramProvider(dim=64)

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingError("simulated outage")
        return self._impl.embed(texts)


@pytest.fixture
def fake_neural(monkeypatch):
    provider = FakeNeuralProvider()
    for target in ("services", "tasks", "views"):
        monkeypatch.setattr(f"apps.matching.{target}.get_provider", lambda: provider, raising=False)
    return provider


@pytest.fixture
def queued(monkeypatch):
    """Capture background embedding jobs instead of running them."""
    from apps.matching import tasks

    jobs = []
    monkeypatch.setattr(tasks.embed_texts, "delay", lambda texts: jobs.append(list(texts)))
    return jobs


@pytest.fixture
def make_matching_seeker(make_seeker, shiraz):
    def _make(skills=(), titles=(), level="ADVANCED", **resume_fields):
        user = make_seeker()
        fields = {
            "city": shiraz,
            "province": shiraz.province,
            "experience_level": "MID",
            "employment_status": "UNEMPLOYED",
            "desired_work_modes": ["REMOTE"],
            "expected_monthly_salary": 30_000_000,
            "introduction": "برنامه‌نویس بک‌اند با تجربه در پایتون و جنگو",
            **resume_fields,
        }
        resume = Resume.objects.create(job_seeker=user.job_seeker_profile, **fields)
        for skill in skills:
            ResumeSkill.objects.create(resume=resume, skill=skill, level=level)
        for title in titles:
            DesiredJobTitle.objects.create(resume=resume, job_title=title)
        return user

    return _make

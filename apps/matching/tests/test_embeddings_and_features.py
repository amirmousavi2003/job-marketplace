import pytest
from django.core.management import call_command

from apps.jobs import selectors as job_selectors
from apps.matching import embeddings, features
from apps.matching.models import EmbeddingCache
from apps.matching.providers import EmbeddingError, get_provider
from apps.matching.providers.base import NoneProvider
from apps.matching.tasks import embed_post, embed_resume, embed_texts
from apps.resumes.selectors import resume_queryset

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ embedding cache
def test_ensure_embeddings_stores_once_and_is_idempotent(fake_neural):
    assert embeddings.ensure_embeddings(fake_neural, ["متن اول", "متن دوم", "متن اول"]) == 2
    assert EmbeddingCache.objects.count() == 2
    assert embeddings.ensure_embeddings(fake_neural, ["متن اول", "متن دوم"]) == 0
    assert len(fake_neural.calls) == 1  # second call needed no provider request


def test_texts_are_sent_in_batches(fake_neural, settings):
    settings.AI_EMBEDDING_BATCH_SIZE = 2
    embeddings.ensure_embeddings(fake_neural, [f"text number {i}" for i in range(5)])
    assert [len(call) for call in fake_neural.calls] == [2, 2, 1]


def test_a_failing_batch_stores_nothing_for_that_batch(fake_neural, settings):
    settings.AI_EMBEDDING_BATCH_SIZE = 2
    embeddings.ensure_embeddings(fake_neural, ["a1 x", "a2 x"])
    fake_neural.fail = True
    with pytest.raises(EmbeddingError):
        embeddings.ensure_embeddings(fake_neural, ["a1 x", "a2 x", "b1 x", "b2 x"])
    assert EmbeddingCache.objects.count() == 2


def test_vectors_are_scoped_to_provider_and_model(fake_neural):
    embeddings.ensure_embeddings(fake_neural, ["مهارت پایتون"])
    h = embeddings.text_hash("مهارت پایتون")
    assert h in embeddings.cached_vectors(fake_neural, [h])
    fake_neural.model = "fake-2"  # a new model must not reuse old vectors
    assert embeddings.cached_vectors(fake_neural, [h]) == {}
    assert embeddings.missing_texts(fake_neural, ["مهارت پایتون"]) == {h: "مهارت پایتون"}


def test_no_provider_means_no_vectors_and_no_fake_ones():
    provider = NoneProvider()
    assert embeddings.cached_vectors(provider, ["x"]) == {}
    assert EmbeddingCache.objects.count() == 0


def test_cosine_basics():
    assert embeddings.cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert embeddings.cosine([1, 0], [0, 1]) == pytest.approx(0)
    assert embeddings.cosine([0, 0], [1, 1]) == 0


# ------------------------------------------------------------------ features
def test_live_resume_and_frozen_snapshot_give_identical_features(
    make_applicant, job, make_application
):
    user = make_applicant()
    application = make_application(user)
    live = features.resume_features(resume_queryset().get(job_seeker=user.job_seeker_profile))
    frozen = features.snapshot_features(application.resume_snapshot)
    assert live == frozen
    assert live.digest() == frozen.digest() and live.text() == frozen.text()


def test_features_change_when_the_resume_changes(make_applicant):
    user = make_applicant()
    before = features.resume_features(resume_queryset().get(job_seeker=user.job_seeker_profile))
    resume = user.job_seeker_profile.resume
    resume.introduction = "متن جدید رزومه"
    resume.save()
    after = features.resume_features(resume_queryset().get(pk=resume.pk))
    assert before.digest() != after.digest() and before.text() != after.text()


def test_post_features_split_required_and_optional_skills(make_post, make_skill):
    a, b = make_skill("Django", "جنگو"), make_skill("Docker", "داکر")
    from apps.jobs.models import JobPostSkill

    post = make_post(published=True, skills=[a, b])
    JobPostSkill.objects.filter(job_post=post, skill=b).update(
        is_required=False, minimum_level="ADVANCED"
    )
    f = features.post_features(job_selectors.base_queryset().get(pk=post.pk))
    assert [s[1] for s in f.required_skills] == ["جنگو"] and f.optional_skills[0][2] == "ADVANCED"
    assert f.post_type == "EMPLOYMENT" and f.salary_max == 20_000_000


def test_text_is_normalized_and_bounded(make_post):
    post = make_post(published=True, description="ك" * 10_000)
    text = features.post_features(job_selectors.base_queryset().get(pk=post.pk)).text()
    assert len(text) <= features.MAX_TEXT_CHARS and "ك" not in text


# ------------------------------------------------------------------ tasks and command
def test_embed_post_task_stores_a_vector_with_the_local_provider(make_post):
    post = make_post(published=True)
    assert (
        embed_post(post.pk) == 1
        and EmbeddingCache.objects.filter(provider="local_ngram").count() == 1
    )
    assert embed_post(post.pk) == 0  # already cached


def test_embed_resume_task(make_applicant):
    user = make_applicant()
    assert embed_resume(user.job_seeker_profile.resume.pk) == 1


def test_tasks_do_nothing_when_no_provider_is_configured(settings, make_post):
    settings.AI_EMBEDDING_PROVIDER = "none"
    post = make_post(published=True)
    assert embed_post(post.pk) == 0 and embed_texts(texts=["x"]) == 0
    assert EmbeddingCache.objects.count() == 0


def test_tasks_ignore_unknown_ids():
    assert embed_post(999999) == 0 and embed_resume(999999) == 0


def test_task_failure_surfaces_as_an_error_for_retry(fake_neural):
    fake_neural.fail = True
    with pytest.raises(EmbeddingError):
        embed_texts(texts=["something to embed"])
    assert EmbeddingCache.objects.count() == 0


def test_compute_embeddings_command(make_post, capsys, settings):
    make_post(published=True)
    make_post(published=True)
    make_post()  # draft: not public, not embedded
    call_command("compute_embeddings")
    assert EmbeddingCache.objects.count() == 2
    call_command("compute_embeddings")
    assert "0 new vector" in capsys.readouterr().out
    settings.AI_EMBEDDING_PROVIDER = "none"
    call_command("compute_embeddings")
    assert "produces no vectors" in capsys.readouterr().out


def test_provider_none_object_is_what_a_broken_config_gives(settings):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"
    settings.AI_EMBEDDING_API_URL = ""
    assert isinstance(get_provider(), NoneProvider)

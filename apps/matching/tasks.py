"""Background work: embedding texts with the configured provider.

The web request never waits for a network embedding call. Failures are retried with backoff;
a provider that is not configured makes these tasks a no-op (nothing is faked)."""

import logging

from celery import shared_task

from apps.jobs import selectors as job_selectors
from apps.resumes.selectors import resume_queryset

from . import embeddings, features
from .providers import EmbeddingError, get_provider

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(EmbeddingError,), retry_backoff=30, retry_backoff_max=900, max_retries=3
)
def embed_texts(texts: list[str]) -> int:
    provider = get_provider()
    if not provider.available:
        return 0
    created = embeddings.ensure_embeddings(provider, texts)
    logger.info("embedded %s texts with %s/%s", created, provider.name, provider.model)
    return created


@shared_task
def embed_post(post_id: int) -> int:
    post = job_selectors.base_queryset().filter(pk=post_id).first()
    if post is None:
        return 0
    return embed_texts(texts=[features.post_features(post).text()])


@shared_task
def embed_resume(resume_id: int) -> int:
    resume = resume_queryset().filter(pk=resume_id).first()
    if resume is None:
        return 0
    return embed_texts(texts=[features.resume_features(resume).text()])


@shared_task
def embed_visible_posts() -> int:
    """Backfill: vectors for every currently public post."""
    posts = list(job_selectors.visible_posts())
    return embed_texts(texts=[features.post_features(p).text() for p in posts])

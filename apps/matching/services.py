"""Orchestrates the matching pipeline: extract -> normalize -> embed -> score -> store."""

import hashlib
import json
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.applications.models import Application
from apps.jobs import selectors as job_selectors
from apps.resumes.selectors import resume_queryset

from . import embeddings, features, scoring
from .models import AIMatch
from .providers import EmbeddingError, EmbeddingProvider, get_provider

DISCLAIMER = (
    "این امتیاز فقط یک شاخص تقریبی و توضیح‌پذیر برای کمک به مرتب‌سازی است و دقت علمی ندارد. "
    "هیچ تصمیمی بر اساس آن خودکار گرفته نمی‌شود؛ تصمیم نهایی همیشه با انسان است."
)


@dataclass
class PostMatch:
    post: object
    result: scoring.MatchResult
    semantic_used: bool


def _lock(name: str, seconds: int = 600) -> bool:
    """True the first time within `seconds`: avoids queueing the same work repeatedly."""
    return cache.add(f"matching:{name}", 1, seconds)


def _request_embeddings(provider: EmbeddingProvider, texts: list[str]) -> bool:
    """Make sure vectors for `texts` will exist. Cheap local providers compute them now;
    network providers get a background task. Returns True when everything is already cached."""
    missing = embeddings.missing_texts(provider, texts)
    if not missing:
        return True
    if provider.inline_ok:
        try:
            embeddings.ensure_embeddings(provider, missing.values())
            return True
        except EmbeddingError:
            return False
    from .tasks import embed_texts

    to_queue = [
        t for h, t in missing.items() if _lock(f"embed:{provider.name}:{provider.model}:{h}")
    ]
    if to_queue:
        embed_texts.delay(to_queue)
    return False


def _semantic_for(provider, resume_text: str, post_texts: dict[int, str]):
    """({post_id: cosine or None}, resume_hash, {post_id: hash}, pending)"""
    if not provider.available:
        return {}, "", {}, False
    texts = [resume_text, *post_texts.values()]
    ready = _request_embeddings(provider, texts)
    hashes = {pid: embeddings.text_hash(t) for pid, t in post_texts.items()}
    resume_hash = embeddings.text_hash(resume_text)
    vectors = embeddings.cached_vectors(provider, [resume_hash, *hashes.values()])
    resume_vector = vectors.get(resume_hash)
    sims = {}
    for pid, h in hashes.items():
        sims[pid] = (
            embeddings.cosine(resume_vector, vectors[h]) if resume_vector and h in vectors else None
        )
    return sims, resume_hash, hashes, not ready


def _inputs_hash(resume_digest, post_digest, provider, resume_text_hash, post_text_hash, used):
    payload = {
        "v": scoring.SCORING_VERSION,
        "cfg": scoring.config(),
        "r": resume_digest,
        "p": post_digest,
        "sem": [provider.name, provider.model, resume_text_hash, post_text_hash] if used else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _score_posts(provider, resume_f, posts) -> tuple[list[PostMatch], dict]:
    post_fs = {p.pk: features.post_features(p) for p in posts}
    sims, resume_hash, post_hashes, pending = _semantic_for(
        provider, resume_f.text(), {pid: f.text() for pid, f in post_fs.items()}
    )
    out, hashes = [], {}
    for post in posts:
        pf = post_fs[post.pk]
        cosine = sims.get(post.pk)
        result = scoring.score_pair(
            resume_f, pf, cosine=cosine, provider_kind=provider.kind, semantic_pending=pending
        )
        used = cosine is not None
        out.append(PostMatch(post, result, used))
        hashes[post.pk] = _inputs_hash(
            resume_f.digest(),
            pf.digest(),
            provider,
            resume_hash,
            post_hashes.get(post.pk, ""),
            used,
        )
    return out, hashes


def _persist(profile, provider, matches: list[PostMatch], hashes: dict) -> None:
    """Upsert only rows whose inputs changed."""
    existing = dict(
        AIMatch.objects.filter(
            job_seeker=profile, job_post_id__in=[m.post.pk for m in matches]
        ).values_list("job_post_id", "inputs_hash")
    )
    now = timezone.now()
    rows = [
        AIMatch(
            job_seeker=profile,
            job_post=m.post,
            score=m.result.score,
            factors=m.result.factors,
            explanation=m.result.reasons,
            flags=m.result.flags,
            provider=provider.name if m.semantic_used else "none",
            model_name=provider.model if m.semantic_used else "",
            semantic_used=m.semantic_used,
            scoring_version=scoring.SCORING_VERSION,
            inputs_hash=hashes[m.post.pk],
            computed_at=now,
        )
        for m in matches
        if existing.get(m.post.pk) != hashes[m.post.pk]
    ]
    if rows:
        AIMatch.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["job_seeker", "job_post"],
            update_fields=[
                "score", "factors", "explanation", "flags", "provider", "model_name",
                "semantic_used", "scoring_version", "inputs_hash", "computed_at",
            ],
        )  # fmt: skip


def _own_resume(profile):
    resume = resume_queryset().filter(job_seeker=profile).first()
    if resume is None:
        raise ValidationError({"resume": ["Create your resume to get recommendations."]})
    return resume


@transaction.atomic
def refresh_matches_for_seeker(profile, post_type: str | None = None) -> list[PostMatch]:
    """Score the seeker's resume against the newest public posts and store the results.
    Never touches applications or anyone's status."""
    provider = get_provider()
    resume_f = features.resume_features(_own_resume(profile))
    posts = job_selectors.visible_posts().exclude(employer__user_id=profile.user_id)
    if post_type:
        posts = posts.filter(post_type=post_type)
    posts = list(posts.order_by("-published_at", "-id")[: settings.MATCHING["MAX_CANDIDATES"]])
    matches, hashes = _score_posts(provider, resume_f, posts)
    _persist(profile, provider, matches, hashes)
    return sorted(matches, key=lambda m: (-m.result.score, -m.post.pk))


@transaction.atomic
def match_for_post(profile, post_id: int) -> PostMatch:
    post = get_object_or_404(job_selectors.visible_posts(), pk=post_id)
    provider = get_provider()
    resume_f = features.resume_features(_own_resume(profile))
    matches, hashes = _score_posts(provider, resume_f, [post])
    _persist(profile, provider, matches, hashes)
    return matches[0]


def rank_applicants(post) -> list[dict]:
    """Assistive ranking of the people who applied to an employment post, from what they
    submitted (the frozen snapshot). Not stored; never changes an application."""
    provider = get_provider()
    applications = list(
        Application.objects.filter(job_post=post).select_related("job_seeker").order_by("-id")[:200]
    )
    post_f = features.post_features(post)
    snapshots = {a.pk: features.snapshot_features(a.resume_snapshot) for a in applications}
    sims, pending = {}, False
    if provider.available and applications:
        post_text = post_f.text()
        texts = [post_text, *[f.text() for f in snapshots.values()]]
        pending = not _request_embeddings(provider, texts)
        post_hash = embeddings.text_hash(post_text)
        vectors = embeddings.cached_vectors(
            provider, [post_hash, *[embeddings.text_hash(f.text()) for f in snapshots.values()]]
        )
        for app_id, f in snapshots.items():
            h = embeddings.text_hash(f.text())
            if post_hash in vectors and h in vectors:
                sims[app_id] = embeddings.cosine(vectors[h], vectors[post_hash])
    rows = []
    for application in applications:
        result = scoring.score_pair(
            snapshots[application.pk],
            post_f,
            cosine=sims.get(application.pk),
            provider_kind=provider.kind,
            semantic_pending=pending,
        )
        rows.append(
            {"application": application, "result": result, "semantic_used": application.pk in sims}
        )
    return sorted(rows, key=lambda r: (-r["result"].score, -r["application"].pk))


def provider_info() -> dict:
    return {**get_provider().info(), "scoring_version": scoring.SCORING_VERSION}

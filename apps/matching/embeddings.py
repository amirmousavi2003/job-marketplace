"""Step 3-4: embedding cache and cosine similarity."""

import hashlib
import math
from collections.abc import Iterable

from django.conf import settings

from .models import EmbeddingCache
from .providers import EmbeddingProvider


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def cached_vectors(provider: EmbeddingProvider, hashes: Iterable[str]) -> dict[str, list[float]]:
    if not provider.available:
        return {}
    rows = EmbeddingCache.objects.filter(
        provider=provider.name, model=provider.model, text_hash__in=list(set(hashes))
    ).values_list("text_hash", "vector")
    return dict(rows)


def missing_texts(provider: EmbeddingProvider, texts: Iterable[str]) -> dict[str, str]:
    """{hash: text} for texts that have no cached vector yet."""
    by_hash = {text_hash(t): t for t in texts if t}
    have = cached_vectors(provider, by_hash)
    return {h: t for h, t in by_hash.items() if h not in have}


def ensure_embeddings(provider: EmbeddingProvider, texts: Iterable[str]) -> int:
    """Embed and store every text that is not cached yet. Raises EmbeddingError on failure and
    stores nothing for the failing batch. Returns how many vectors were created."""
    todo = list(missing_texts(provider, texts).items())
    batch = max(1, settings.AI_EMBEDDING_BATCH_SIZE)
    created = 0
    for start in range(0, len(todo), batch):
        chunk = todo[start : start + batch]
        vectors = provider.embed([text for _, text in chunk])
        EmbeddingCache.objects.bulk_create(
            [
                EmbeddingCache(
                    provider=provider.name, model=provider.model, text_hash=h, vector=vector
                )
                for (h, _), vector in zip(chunk, vectors, strict=True)
            ],
            ignore_conflicts=True,
        )
        created += len(chunk)
    return created

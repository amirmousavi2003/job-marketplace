"""Offline, key-free text vectors for Persian/English: hashed character n-grams + words.

This is NOT a neural embedding. Cosine similarity of these vectors measures how much two texts
share words and word fragments (so "برنامه‌نویس" and "برنامه نویسی" are close, "جنگو" and
"Django" are not). The API labels it as kind="lexical"."""

import math
import zlib
from collections.abc import Sequence

from apps.common.text import normalize_text

from .base import EmbeddingProvider

NGRAM_SIZES = (3, 4)
WORD_WEIGHT = 2.0


class LocalNgramProvider(EmbeddingProvider):
    name = "local_ngram"
    kind = "lexical"
    inline_ok = True

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.model = f"char-ngram-hash-{dim}-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _bucket(self, token: str) -> int:
        return zlib.crc32(token.encode("utf-8")) % self.dim  # stable across processes

    def _vector(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for word in normalize_text(text).split():
            counts[self._bucket("w:" + word)] = (
                counts.get(self._bucket("w:" + word), 0.0) + WORD_WEIGHT
            )
            padded = f" {word} "
            for size in NGRAM_SIZES:
                for i in range(len(padded) - size + 1):
                    bucket = self._bucket(padded[i : i + size])
                    counts[bucket] = counts.get(bucket, 0.0) + 1.0
        vector = [0.0] * self.dim
        for bucket, count in counts.items():
            vector[bucket] = 1.0 + math.log(count)  # sublinear term frequency
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [round(v / norm, 6) for v in vector]

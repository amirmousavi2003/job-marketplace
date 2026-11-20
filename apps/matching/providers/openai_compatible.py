"""Client for any service that implements the OpenAI-style `POST {base}/embeddings` API.
Uses only the standard library. The API key is sent as a Bearer header and never logged."""

import json
import math
import urllib.error
import urllib.request
from collections.abc import Sequence
from urllib.parse import urlparse

from .base import EmbeddingError, EmbeddingProvider

MAX_RESPONSE_BYTES = 20 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("AI_EMBEDDING_API_URL must be an http(s) URL.")
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
        raise ValueError(
            "AI_EMBEDDING_API_URL must use https (http is allowed only for localhost)."
        )
    return url.rstrip("/")


class OpenAICompatibleProvider(EmbeddingProvider):
    name = "openai_compatible"
    kind = "neural"
    inline_ok = False  # network call: run in the background

    def __init__(self, url: str, api_key: str, model: str, timeout: int = 20):
        self.url = validate_url(url)
        self._api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - scheme validated in validate_url
            f"{self.url}/embeddings",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise EmbeddingError(f"Embedding service answered HTTP {exc.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EmbeddingError("Embedding service is unreachable.") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise EmbeddingError("Embedding response is too large.")
        return self._parse(raw, expected=len(texts))

    @staticmethod
    def _parse(raw: bytes, expected: int) -> list[list[float]]:
        try:
            items = sorted(json.loads(raw)["data"], key=lambda item: item["index"])
            vectors = [[float(x) for x in item["embedding"]] for item in items]
        except (ValueError, KeyError, TypeError):
            raise EmbeddingError("Embedding service returned an unexpected response.") from None
        if len(vectors) != expected or len({len(v) for v in vectors}) != 1 or not vectors[0]:
            raise EmbeddingError("Embedding service returned an unexpected number of vectors.")
        if not all(math.isfinite(x) for v in vectors for x in v):
            raise EmbeddingError("Embedding service returned invalid numbers.")
        return vectors

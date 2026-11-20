from django.conf import settings

from .base import EmbeddingError, EmbeddingProvider, NoneProvider
from .local_ngram import LocalNgramProvider
from .openai_compatible import OpenAICompatibleProvider, validate_url

__all__ = ["EmbeddingError", "EmbeddingProvider", "get_provider", "provider_problems"]


def provider_problems() -> list[str]:
    """Human-readable configuration problems (used by the system check and get_provider)."""
    name = (settings.AI_EMBEDDING_PROVIDER or "none").lower()
    if name in {"none", "local_ngram"}:
        return []
    if name != "openai_compatible":
        return [
            f"Unknown AI_EMBEDDING_PROVIDER '{name}'. Use none, local_ngram or openai_compatible."
        ]
    problems = [
        f"AI_EMBEDDING_{var} is not set."
        for var, value in (
            ("API_URL", settings.AI_EMBEDDING_API_URL),
            ("API_KEY", settings.AI_EMBEDDING_API_KEY),
            ("MODEL", settings.AI_EMBEDDING_MODEL),
        )
        if not value
    ]
    if settings.AI_EMBEDDING_API_URL:
        try:
            validate_url(settings.AI_EMBEDDING_API_URL)
        except ValueError as exc:
            problems.append(str(exc))
    return problems


def get_provider() -> EmbeddingProvider:
    """The configured provider. A broken configuration never pretends to work: it yields the
    `none` provider with the reason, so results are honestly marked as structured-only."""
    problems = provider_problems()
    if problems:
        return NoneProvider(" ".join(problems))
    name = (settings.AI_EMBEDDING_PROVIDER or "none").lower()
    if name == "local_ngram":
        return LocalNgramProvider()
    if name == "openai_compatible":
        return OpenAICompatibleProvider(
            settings.AI_EMBEDDING_API_URL,
            settings.AI_EMBEDDING_API_KEY,
            settings.AI_EMBEDDING_MODEL,
            settings.AI_EMBEDDING_TIMEOUT_SECONDS,
        )
    return NoneProvider()

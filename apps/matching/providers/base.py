from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingError(Exception):
    """The embedding backend failed (network, HTTP error, bad response). Never contains secrets."""


class EmbeddingProvider(ABC):
    """Turns texts into vectors. Business logic only depends on this interface, so a provider can
    be swapped (settings) without touching the matching code.

    kind: "none" (no vectors), "lexical" (character n-gram overlap, not a neural model),
          "neural" (a real embedding model behind an API).
    """

    name: str = "none"
    model: str = ""
    kind: str = "none"
    inline_ok: bool = False  # True: cheap and local, safe to run inside a web request
    reason: str = ""  # why it is unavailable, when it is

    @property
    def available(self) -> bool:
        return self.kind != "none"

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def info(self) -> dict:
        """Safe to show to API clients: no URL, no key."""
        return {
            "provider": self.name,
            "model": self.model,
            "kind": self.kind,
            "semantic_available": self.available,
            "reason": self.reason,
        }


class NoneProvider(EmbeddingProvider):
    """No semantic component. Matching falls back to structured scoring only."""

    name = "none"
    kind = "none"

    def __init__(self, reason: str = "AI_EMBEDDING_PROVIDER is 'none'."):
        self.reason = reason

    def embed(self, texts):
        raise EmbeddingError(self.reason)

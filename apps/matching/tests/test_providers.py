import io
import json
import urllib.error

import pytest
from django.core.checks import run_checks

from apps.matching.embeddings import cosine
from apps.matching.providers import EmbeddingError, get_provider
from apps.matching.providers.base import NoneProvider
from apps.matching.providers.local_ngram import LocalNgramProvider
from apps.matching.providers.openai_compatible import OpenAICompatibleProvider, validate_url

RESUME = "برنامه‌نویس بک‌اند. مهارت‌ها: پایتون جنگو پستگرس. تجربه: توسعه API و پایگاه داده"
RELEVANT = "برنامه‌نویس جنگو. نیازمند توسعه‌دهنده بک‌اند مسلط به پایتون و پستگرس برای توسعه API"
UNRELATED = "حسابدار ارشد. تنظیم اظهارنامه مالیاتی و دفاتر قانونی و صورت‌های مالی شرکت"


# ------------------------------------------------------------------ local n-gram
def test_local_vectors_are_deterministic_unit_length_and_sized():
    p = LocalNgramProvider()
    a, b = p.embed([RESUME])[0], p.embed([RESUME])[0]
    assert a == b and len(a) == 1024
    assert abs(sum(x * x for x in a) - 1) < 1e-3


def test_local_provider_is_honest_about_what_it_is():
    p = LocalNgramProvider()
    info = p.info()
    assert (info["kind"], info["provider"], info["semantic_available"]) == (
        "lexical",
        "local_ngram",
        True,
    )
    assert p.inline_ok is True


def test_local_empty_text_gives_zero_vector_not_a_crash():
    assert sum(LocalNgramProvider().embed([""])[0]) == 0
    assert cosine(LocalNgramProvider().embed([""])[0], LocalNgramProvider().embed([RESUME])[0]) == 0


def test_local_normalizes_persian_variants():
    p = LocalNgramProvider()
    a = p.embed(["نرم‌افزار كيبورد ۱۲۳"])[0]
    b = p.embed(["نرم افزار کیبورد 123"])[0]
    assert cosine(a, b) > 0.999


def test_local_ranks_related_text_above_unrelated():
    p = LocalNgramProvider()
    r, good, bad = (p.embed([t])[0] for t in (RESUME, RELEVANT, UNRELATED))
    assert cosine(r, good) > cosine(r, bad) + 0.2


def test_local_cannot_cross_languages_and_does_not_pretend_to():
    p = LocalNgramProvider()
    persian, english = p.embed(["برنامه‌نویس جنگو"])[0], p.embed(["Django developer"])[0]
    assert cosine(persian, english) < 0.2  # lexical only: documented limitation


# ------------------------------------------------------------------ OpenAI-compatible
class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok_body(vectors):
    return json.dumps(
        {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]}
    ).encode()


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(
        "https://ai.example.ir/v1/", "sk-secret-key", "emb-1", timeout=7
    )


def patch_urlopen(monkeypatch, result):
    seen = {}

    def fake(request, timeout=None):
        seen.update(
            url=request.full_url,
            headers=dict(request.header_items()),
            body=request.data,
            timeout=timeout,
            method=request.get_method(),
        )
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return seen


def test_request_shape_and_response_order(provider, monkeypatch):
    seen = patch_urlopen(
        monkeypatch,
        json.dumps(
            {"data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}
        ).encode(),
    )
    vectors = provider.embed(["a", "b"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]  # re-ordered by index
    assert seen["url"] == "https://ai.example.ir/v1/embeddings" and seen["method"] == "POST"
    assert seen["headers"]["Authorization"] == "Bearer sk-secret-key" and seen["timeout"] == 7
    assert json.loads(seen["body"]) == {"model": "emb-1", "input": ["a", "b"]}


@pytest.mark.parametrize("code", [401, 429, 500])
def test_http_errors_become_embedding_errors_without_leaking_the_key(provider, monkeypatch, code):
    patch_urlopen(
        monkeypatch,
        urllib.error.HTTPError("https://x", code, "msg", {}, io.BytesIO(b"sk-secret-key echoed")),
    )
    with pytest.raises(EmbeddingError) as exc:
        provider.embed(["a"])
    assert str(code) in str(exc.value) and "sk-secret-key" not in str(exc.value)


@pytest.mark.parametrize(
    "error", [urllib.error.URLError("dns"), TimeoutError(), ConnectionResetError()]
)
def test_network_failures_become_embedding_errors(provider, monkeypatch, error):
    patch_urlopen(monkeypatch, error)
    with pytest.raises(EmbeddingError, match="unreachable"):
        provider.embed(["a"])


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        json.dumps({"data": [{"index": 0}]}).encode(),
        ok_body([[1.0], [1.0]]),  # 2 vectors for 1 text
        ok_body([[]]),
        json.dumps({"data": [{"index": 0, "embedding": ["x"]}]}).encode(),
        b'{"data": [{"index": 0, "embedding": [NaN]}]}',
    ],
)
def test_bad_responses_are_rejected(provider, monkeypatch, body):
    patch_urlopen(monkeypatch, body)
    with pytest.raises(EmbeddingError):
        provider.embed(["a"])


def test_mixed_dimensions_are_rejected(provider, monkeypatch):
    patch_urlopen(monkeypatch, ok_body([[1.0, 2.0], [1.0]]))
    with pytest.raises(EmbeddingError):
        provider.embed(["a", "b"])


@pytest.mark.parametrize(
    "bad", ["ftp://x.ir/v1", "x.ir/v1", "", "javascript:alert(1)", "http://ai.example.ir/v1"]
)
def test_url_must_be_https_or_local(bad):
    with pytest.raises(ValueError):
        validate_url(bad)


@pytest.mark.parametrize(
    "good", ["https://ai.example.ir/v1", "http://localhost:8080/v1", "http://127.0.0.1:11434/v1"]
)
def test_good_urls(good):
    assert validate_url(good) == good


# ------------------------------------------------------------------ configuration
def test_default_provider_is_local(settings):
    settings.AI_EMBEDDING_PROVIDER = "local_ngram"
    assert get_provider().name == "local_ngram"


def test_none_provider_is_explicit_and_cannot_embed(settings):
    settings.AI_EMBEDDING_PROVIDER = "none"
    p = get_provider()
    assert isinstance(p, NoneProvider) and not p.available
    with pytest.raises(EmbeddingError):
        p.embed(["x"])


def test_unknown_provider_degrades_to_none_with_a_reason(settings):
    settings.AI_EMBEDDING_PROVIDER = "magic"
    p = get_provider()
    assert not p.available and "magic" in p.reason


def test_incomplete_openai_config_never_pretends_to_work(settings):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"
    settings.AI_EMBEDDING_API_URL, settings.AI_EMBEDDING_API_KEY, settings.AI_EMBEDDING_MODEL = (
        "",
        "",
        "",
    )
    p = get_provider()
    assert not p.available
    assert "API_URL" in p.reason and "API_KEY" in p.reason and "MODEL" in p.reason
    ids = [w.id for w in run_checks() if w.id.startswith("matching.")]
    assert ids.count("matching.W001") == 3


def test_complete_openai_config_builds_the_network_provider(settings):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"
    settings.AI_EMBEDDING_API_URL = "https://ai.example.ir/v1"
    settings.AI_EMBEDDING_API_KEY = "k"
    settings.AI_EMBEDDING_MODEL = "m"
    p = get_provider()
    assert isinstance(p, OpenAICompatibleProvider) and p.kind == "neural" and p.inline_ok is False
    assert not [w for w in run_checks() if w.id.startswith("matching.")]


def test_provider_info_never_exposes_url_or_key(settings):
    settings.AI_EMBEDDING_PROVIDER = "openai_compatible"
    settings.AI_EMBEDDING_API_URL = "https://ai.example.ir/v1"
    settings.AI_EMBEDDING_API_KEY = "sk-very-secret"
    settings.AI_EMBEDDING_MODEL = "emb"
    text = json.dumps(get_provider().info())
    assert "sk-very-secret" not in text and "ai.example.ir" not in text and "emb" in text

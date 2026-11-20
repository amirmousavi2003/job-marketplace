from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from .providers import provider_problems


@register()
def check_embedding_provider(app_configs, **kwargs):
    """A broken AI configuration never crashes the site: matching falls back to structured-only
    scores. This makes the problem visible at startup instead of silent."""
    return [
        CheckWarning(problem, hint="Matching will use structured scoring only.", id="matching.W001")
        for problem in provider_problems()
    ]

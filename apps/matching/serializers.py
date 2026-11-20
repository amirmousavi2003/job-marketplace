from rest_framework import serializers

from apps.jobs.serializers import PublicJobPostListSerializer

from . import scoring
from .services import DISCLAIMER, PostMatch, provider_info


class ReasonSerializer(serializers.Serializer):
    code = serializers.CharField()
    polarity = serializers.ChoiceField(choices=["positive", "negative", "info"])
    params = serializers.JSONField()
    text_fa = serializers.CharField()


class ProviderInfoSerializer(serializers.Serializer):
    provider = serializers.CharField()
    model = serializers.CharField()
    kind = serializers.ChoiceField(choices=["none", "lexical", "neural"])
    semantic_available = serializers.BooleanField()
    reason = serializers.CharField()
    scoring_version = serializers.CharField()


class MatchSummarySerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    semantic_used = serializers.BooleanField()
    flags = serializers.ListField(child=serializers.CharField())
    reasons = ReasonSerializer(many=True, help_text="The most informative reasons (max 3).")


class RecommendationSerializer(MatchSummarySerializer):
    post = PublicJobPostListSerializer()


class MatchDetailSerializer(MatchSummarySerializer):
    post = PublicJobPostListSerializer()
    factors = serializers.JSONField(help_text="Per-factor value (0..1), weight and details.")
    all_reasons = ReasonSerializer(many=True)
    matching = ProviderInfoSerializer()
    disclaimer = serializers.CharField()


class CandidateSerializer(MatchSummarySerializer):
    application_id = serializers.IntegerField()
    status = serializers.CharField()
    applicant = serializers.DictField(child=serializers.CharField())


class RecomputeResultSerializer(serializers.Serializer):
    matches = serializers.IntegerField()
    semantic = serializers.ChoiceField(choices=["used", "pending", "unavailable"])
    matching = ProviderInfoSerializer()


def summary(result: scoring.MatchResult, semantic_used: bool) -> dict:
    return {
        "score": result.score,
        "semantic_used": semantic_used,
        "flags": result.flags,
        "reasons": scoring.top_reasons(result.reasons),
    }


def recommendation_row(match: PostMatch, context) -> dict:
    return {
        **summary(match.result, match.semantic_used),
        "post": PublicJobPostListSerializer(match.post, context=context).data,
    }


def match_detail(match: PostMatch, context) -> dict:
    return {
        **recommendation_row(match, context),
        "factors": match.result.factors,
        "all_reasons": match.result.reasons,
        "matching": provider_info(),
        "disclaimer": DISCLAIMER,
    }

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.jobs import selectors as job_selectors
from apps.jobs.models import PostType
from apps.profiles.permissions import IsEmployer, IsJobSeeker

from . import serializers as sz
from . import services
from .providers import get_provider


class StatusView(GenericAPIView):
    """Which scoring engine is active (no secrets)."""

    permission_classes = [IsAuthenticated]
    serializer_class = sz.ProviderInfoSerializer
    pagination_class = None

    def get(self, request):
        return Response({**services.provider_info(), "disclaimer": services.DISCLAIMER})


class RecommendationsView(GenericAPIView):
    """Public posts ranked by compatibility with the caller's resume. Assistive only."""

    permission_classes = [IsJobSeeker]
    serializer_class = sz.RecommendationSerializer
    filter_backends: list = []

    @extend_schema(
        parameters=[
            OpenApiParameter("type", str, enum=[c for c, _ in PostType.choices]),
            OpenApiParameter("min_score", int, description="0 to 100"),
        ],
        responses=sz.RecommendationSerializer(many=True),
    )
    def get(self, request):
        post_type = request.query_params.get("type") or None
        if post_type and post_type not in PostType.values:
            raise ValidationError({"type": ["Use EMPLOYMENT or PROJECT."]})
        min_score = request.query_params.get("min_score", "0")
        if not min_score.isdigit() or int(min_score) > 100:
            raise ValidationError({"min_score": ["Use a number from 0 to 100."]})
        matches = [
            m
            for m in services.refresh_matches_for_seeker(request.user.job_seeker_profile, post_type)
            if m.result.score >= int(min_score)
        ]
        page = self.paginate_queryset(matches)
        context = {"request": request}
        response = self.get_paginated_response([sz.recommendation_row(m, context) for m in page])
        response.data["matching"] = services.provider_info()
        response.data["disclaimer"] = services.DISCLAIMER
        return response


class JobMatchView(GenericAPIView):
    """Your own score for one public post, with every factor and reason."""

    permission_classes = [IsJobSeeker]
    serializer_class = sz.MatchDetailSerializer

    def get(self, request, pk):
        match = services.match_for_post(request.user.job_seeker_profile, pk)
        return Response(sz.match_detail(match, {"request": request}))


class CandidatesView(GenericAPIView):
    """For the owner of an employment post: applicants ordered by compatibility. A hint for
    reading order. It does not change any application and nobody is filtered out."""

    permission_classes = [IsEmployer]
    serializer_class = sz.CandidateSerializer
    pagination_class = None

    @extend_schema(
        responses=inline_serializer(
            "CandidateList",
            {
                "results": sz.CandidateSerializer(many=True),
                "matching": sz.ProviderInfoSerializer(),
                "disclaimer": drf.CharField(),
            },
        )
    )
    def get(self, request, pk):
        post = get_object_or_404(job_selectors.owned_posts(request.user.employer_profile), pk=pk)
        if post.post_type != PostType.EMPLOYMENT:
            raise ValidationError(
                {"detail": "Only employment posts have applicants with resumes to compare."}
            )
        rows = [
            {
                "application_id": row["application"].pk,
                "status": row["application"].status,
                "applicant": {
                    "first_name": row["application"].job_seeker.first_name,
                    "last_name": row["application"].job_seeker.last_name,
                },
                **sz.summary(row["result"], row["semantic_used"]),
            }
            for row in services.rank_applicants(post)
        ]
        return Response(
            {
                "results": rows,
                "matching": services.provider_info(),
                "disclaimer": services.DISCLAIMER,
            }
        )


class RecomputeView(GenericAPIView):
    """Refresh your matches now. Embeddings from a network provider are produced in the
    background, so `semantic` can be `pending` until they are ready."""

    permission_classes = [IsJobSeeker]
    serializer_class = sz.RecomputeResultSerializer
    throttle_scope = "matching_recompute"

    def post(self, request):
        matches = services.refresh_matches_for_seeker(request.user.job_seeker_profile)
        provider = get_provider()
        if not provider.available:
            semantic = "unavailable"
        elif all(m.semantic_used for m in matches):
            semantic = "used"
        else:
            semantic = "pending"
        return Response(
            {"matches": len(matches), "semantic": semantic, "matching": services.provider_info()}
        )

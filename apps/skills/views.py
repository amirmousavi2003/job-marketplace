from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from . import selectors, services
from . import serializers as sz
from .models import JobCategory


class JobCategoryListView(ListAPIView):
    """Public. Optional ?parent=<id> (or ?parent=root for top-level only)."""

    serializer_class = sz.JobCategorySerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = None
    filter_backends: list = []

    def get_queryset(self):
        qs = JobCategory.objects.filter(is_active=True)
        parent = self.request.query_params.get("parent")
        if parent == "root":
            qs = qs.filter(parent__isnull=True)
        elif parent and parent.isdigit():
            qs = qs.filter(parent_id=int(parent))
        return qs


# ---------- catalogue search (skills / job titles) ----------
class _CatalogueSearchView(ListAPIView):
    """GET ?search=<text>. Matches names and aliases in Persian or English."""

    permission_classes = [IsAuthenticated]
    filter_backends: list = []
    kind: services.Kind

    def get_queryset(self):
        return selectors.search_catalogue(self.kind, self.request.query_params.get("search", ""))


class SkillListView(_CatalogueSearchView):
    serializer_class = sz.SkillSerializer
    kind = services.SKILL


class JobTitleListView(_CatalogueSearchView):
    serializer_class = sz.JobTitleSerializer
    kind = services.JOB_TITLE


# ---------- user suggestions ----------
class _MySuggestionsView(ListCreateAPIView):
    """GET: my suggestions. POST: suggest a new term (goes to admin review)."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "suggestions"
    filter_backends: list = []
    kind: services.Kind
    output_serializer = None

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get_serializer_class(self):
        if self.request.method == "POST":
            return sz.SuggestionCreateSerializer
        return self.output_serializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.kind.suggestion.objects.none()
        return self.kind.suggestion.objects.filter(suggested_by=self.request.user)

    def create(self, request, *args, **kwargs):
        data = sz.SuggestionCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        suggestion = services.submit_suggestion(
            self.kind, user=request.user, text=data.validated_data["text"]
        )
        return Response(self.output_serializer(suggestion).data, status=status.HTTP_201_CREATED)


class MySkillSuggestionsView(_MySuggestionsView):
    kind = services.SKILL
    output_serializer = sz.SkillSuggestionSerializer


class MyJobTitleSuggestionsView(_MySuggestionsView):
    kind = services.JOB_TITLE
    output_serializer = sz.JobTitleSuggestionSerializer


# ---------- admin moderation ----------
class _AdminSuggestionListView(ListAPIView):
    """Staff only. ?status=PENDING|APPROVED|REJECTED"""

    permission_classes = [IsAdminUser]
    filter_backends: list = []
    kind: services.Kind

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.kind.suggestion.objects.none()
        qs = self.kind.suggestion.objects.select_related(
            "suggested_by", "reviewed_by", self.kind.result_field
        )
        wanted = self.request.query_params.get("status")
        if wanted:
            if wanted.upper() not in {"PENDING", "APPROVED", "REJECTED"}:
                raise ValidationError({"status": ["Invalid status."]})
            qs = qs.filter(status=wanted.upper())
        return qs


class _AdminSuggestionActionView(GenericAPIView):
    permission_classes = [IsAdminUser]
    kind: services.Kind
    output_serializer = None

    def get_suggestion(self, pk):
        return get_object_or_404(self.kind.suggestion.objects.all(), pk=pk)


class _ApproveView(_AdminSuggestionActionView):
    serializer_class = sz.SuggestionApproveSerializer

    def post(self, request, pk):
        suggestion = self.get_suggestion(pk)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        existing = None
        if data.validated_data.get("existing_id"):
            existing = get_object_or_404(
                self.kind.entry.objects.filter(is_active=True),
                pk=data.validated_data["existing_id"],
            )
        result = services.approve_suggestion(
            self.kind,
            suggestion,
            reviewer=request.user,
            existing=existing,
            name_fa=data.validated_data.get("name_fa", ""),
            name_en=data.validated_data.get("name_en", ""),
            aliases=data.validated_data.get("aliases", []),
            note=data.validated_data.get("note", ""),
        )
        return Response(self.output_serializer(result).data)


class _RejectView(_AdminSuggestionActionView):
    serializer_class = sz.SuggestionRejectSerializer

    def post(self, request, pk):
        suggestion = self.get_suggestion(pk)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = services.reject_suggestion(
            self.kind, suggestion, reviewer=request.user, note=data.validated_data["note"]
        )
        return Response(self.output_serializer(result).data)


class AdminSkillSuggestionListView(_AdminSuggestionListView):
    kind = services.SKILL
    serializer_class = sz.AdminSkillSuggestionSerializer


class AdminSkillSuggestionApproveView(_ApproveView):
    kind = services.SKILL
    output_serializer = sz.AdminSkillSuggestionSerializer


class AdminSkillSuggestionRejectView(_RejectView):
    kind = services.SKILL
    output_serializer = sz.AdminSkillSuggestionSerializer


class AdminJobTitleSuggestionListView(_AdminSuggestionListView):
    kind = services.JOB_TITLE
    serializer_class = sz.AdminJobTitleSuggestionSerializer


class AdminJobTitleSuggestionApproveView(_ApproveView):
    kind = services.JOB_TITLE
    output_serializer = sz.AdminJobTitleSuggestionSerializer


class AdminJobTitleSuggestionRejectView(_RejectView):
    kind = services.JOB_TITLE
    output_serializer = sz.AdminJobTitleSuggestionSerializer

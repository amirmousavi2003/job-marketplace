from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.jobs import selectors
from apps.jobs.filters import MyPostFilter
from apps.jobs.models import JobPost, ModerationStatus

from . import serializers as sz
from . import services
from .models import ModerationHistory


def _admin_posts():
    return selectors.base_queryset().prefetch_related("moderation_history__actor")


class AdminJobListView(ListAPIView):
    """Staff only. ?moderation_status=PENDING_REVIEW shows the review queue, oldest first."""

    serializer_class = sz.AdminJobPostListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MyPostFilter

    def get_queryset(self):
        qs = JobPost.objects.select_related("employer__user")
        if self.request.query_params.get("moderation_status") == ModerationStatus.PENDING_REVIEW:
            return qs.order_by("updated_at", "id")
        return qs.order_by("-updated_at", "-id")


class AdminJobDetailView(RetrieveAPIView):
    serializer_class = sz.AdminJobPostSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return _admin_posts()


class _ReviewView(GenericAPIView):
    permission_classes = [IsAdminUser]

    def review(self, post, reviewer, data):
        raise NotImplementedError

    def post(self, request, pk):
        post = get_object_or_404(JobPost.objects.all(), pk=pk)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        self.review(post, request.user, data.validated_data)
        fresh = get_object_or_404(_admin_posts(), pk=pk)
        return Response(sz.AdminJobPostSerializer(fresh).data)


class AdminJobApproveView(_ReviewView):
    serializer_class = sz.JobApproveSerializer

    def review(self, post, reviewer, data):
        services.approve(post, reviewer=reviewer, note=data.get("note", ""))


class AdminJobRejectView(_ReviewView):
    serializer_class = sz.JobRejectSerializer

    def review(self, post, reviewer, data):
        services.reject(post, reviewer=reviewer, reason=data["reason"])


class AdminModerationHistoryView(ListAPIView):
    serializer_class = sz.ModerationHistorySerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    filter_backends: list = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ModerationHistory.objects.none()
        get_object_or_404(JobPost.objects.all(), pk=self.kwargs["pk"])
        return ModerationHistory.objects.filter(job_post_id=self.kwargs["pk"]).select_related(
            "actor"
        )

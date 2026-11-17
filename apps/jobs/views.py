from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response

from apps.moderation import services as moderation
from apps.profiles.permissions import IsEmployer

from . import selectors, services
from .filters import JobPostFilter, MyPostFilter
from .models import PostType
from .serializers import (
    WRITE_SERIALIZERS,
    OwnerJobPostSerializer,
    PublicJobPostListSerializer,
    PublicJobPostSerializer,
)


def _owner_response(post, status_code=status.HTTP_200_OK):
    fresh = selectors.base_queryset().get(pk=post.pk)
    return Response(OwnerJobPostSerializer(fresh).data, status=status_code)


class _JobSearchView(ListAPIView):
    """Shared search behaviour: only publicly visible posts, filtered by JobPostFilter."""

    serializer_class = PublicJobPostListSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = JobPostFilter
    post_type: str | None = None

    def get_queryset(self):
        qs = selectors.visible_posts().order_by("-published_at", "-id")
        return qs.filter(post_type=self.post_type) if self.post_type else qs


class PublicJobListView(_JobSearchView):
    """GET /jobs/ — search all published posts (employment and projects). Public."""

    permission_classes = [AllowAny]
    authentication_classes: list = []


class _TypedListCreateView(_JobSearchView):
    """GET: public list of one type. POST: an employer creates a draft of that type."""

    throttle_scope = "job_create"

    def get_permissions(self):
        return [IsEmployer()] if self.request.method == "POST" else [AllowAny()]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get_serializer_class(self):
        if self.request.method == "POST":
            return WRITE_SERIALIZERS[self.post_type]
        return PublicJobPostListSerializer

    def post(self, request):
        serializer = WRITE_SERIALIZERS[self.post_type](
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        post = serializer.save()
        return _owner_response(post, status.HTTP_201_CREATED)


class EmploymentListCreateView(_TypedListCreateView):
    post_type = PostType.EMPLOYMENT


class ProjectListCreateView(_TypedListCreateView):
    post_type = PostType.PROJECT


class MyPostsView(ListAPIView):
    """GET /jobs/mine/ — the employer's own posts in every state."""

    serializer_class = OwnerJobPostSerializer
    permission_classes = [IsEmployer]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MyPostFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return selectors.base_queryset().none()
        return selectors.owned_posts(self.request.user.employer_profile).order_by("-id")


class JobPostDetailView(GenericAPIView):
    """GET (public if visible, else owner) / PATCH (owner) / DELETE (owner)."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method in SAFE_METHODS else [IsEmployer()]

    def get_serializer_class(self):
        return PublicJobPostSerializer

    def _owned(self):
        return get_object_or_404(
            selectors.owned_posts(self.request.user.employer_profile), pk=self.kwargs["pk"]
        )

    def get(self, request, pk):
        post = selectors.get_post_for_viewer(pk, request.user)
        owner = (
            getattr(request.user, "employer_profile", None)
            if request.user.is_authenticated
            else None
        )
        serializer_class = (
            OwnerJobPostSerializer
            if owner and post.employer_id == owner.pk
            else PublicJobPostSerializer
        )
        return Response(serializer_class(post).data)

    def patch(self, request, pk):
        post = self._owned()
        serializer = WRITE_SERIALIZERS[post.post_type](
            post, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _owner_response(post)

    def delete(self, request, pk):
        services.delete_job_post(self._owned())
        return Response(status=status.HTTP_204_NO_CONTENT)


class _OwnerActionView(GenericAPIView):
    """POST /jobs/{id}/<action>/ — owner-only state changes."""

    permission_classes = [IsEmployer]
    serializer_class = OwnerJobPostSerializer

    def act(self, request, post):
        raise NotImplementedError

    def post(self, request, pk):
        post = get_object_or_404(selectors.owned_posts(request.user.employer_profile), pk=pk)
        self.act(request, post)
        return _owner_response(post)


class SubmitView(_OwnerActionView):
    def act(self, request, post):
        moderation.submit_for_review(post, actor=request.user)


class DeactivateView(_OwnerActionView):
    def act(self, request, post):
        services.deactivate(post)


class ActivateView(_OwnerActionView):
    def act(self, request, post):
        services.activate(post)


class RenewView(_OwnerActionView):
    def act(self, request, post):
        services.renew(post)

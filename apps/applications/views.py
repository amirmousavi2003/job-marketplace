from dataclasses import dataclass

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.jobs import selectors as job_selectors
from apps.jobs.models import PostType
from apps.profiles.permissions import IsEmployer, IsJobSeeker

from . import selectors, services
from . import serializers as sz
from .filters import ApplicationFilter, ProposalFilter


@dataclass(frozen=True)
class Kind:
    """Everything that differs between applications and proposals; the views are written once."""

    machine: services.Machine
    queryset: callable
    list_serializer: type
    detail_serializer: type
    create_serializer: type
    transition_serializer: type
    history_serializer: type
    filterset: type
    post_type: str
    other_noun: str


APPLICATIONS = Kind(
    services.APPLICATION,
    selectors.application_queryset,
    sz.ApplicationSerializer,
    sz.ApplicationDetailSerializer,
    sz.ApplicationCreateSerializer,
    sz.ApplicationTransitionSerializer,
    sz.ApplicationHistorySerializer,
    ApplicationFilter,
    PostType.EMPLOYMENT,
    "proposals",
)
PROPOSALS = Kind(
    services.PROPOSAL,
    selectors.proposal_queryset,
    sz.ProposalSerializer,
    sz.ProposalSerializer,
    sz.ProposalCreateSerializer,
    sz.ProposalTransitionSerializer,
    sz.ProposalHistorySerializer,
    ProposalFilter,
    PostType.PROJECT,
    "applications",
)


def _list_queryset(kind: Kind):
    qs = kind.queryset()
    return qs.defer("resume_snapshot") if kind is APPLICATIONS else qs


class _MineView(ListAPIView):
    """The job seeker's own submissions."""

    kind: Kind
    permission_classes = [IsJobSeeker]
    filter_backends = [DjangoFilterBackend]

    @property
    def filterset_class(self):
        return self.kind.filterset

    def get_serializer_class(self):
        return self.kind.list_serializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": services.APPLICANT}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.kind.machine.model.objects.none()
        return _list_queryset(self.kind).filter(job_seeker=self.request.user.job_seeker_profile)


class _ForPostView(ListAPIView):
    """GET: the post owner lists what they received. POST: a job seeker submits."""

    kind: Kind
    throttle_scope = "apply"
    filter_backends = [DjangoFilterBackend]

    @property
    def filterset_class(self):
        return self.kind.filterset

    def get_permissions(self):
        return [IsJobSeeker()] if self.request.method == "POST" else [IsEmployer()]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get_serializer_class(self):
        if self.request.method == "POST":
            return self.kind.create_serializer
        return self.kind.list_serializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": services.EMPLOYER}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.kind.machine.model.objects.none()
        post = get_object_or_404(
            job_selectors.owned_posts(self.request.user.employer_profile), pk=self.kwargs["post_id"]
        )
        if post.post_type != self.kind.post_type:
            noun = self.kind.machine.model._meta.verbose_name_plural
            raise ValidationError(
                {"detail": f"This post has no {noun}. Look at its {self.kind.other_noun}."}
            )
        return _list_queryset(self.kind).filter(job_post=post)


class _PartyObjectMixin:
    """Open one object as its applicant or the post owner (404 for everyone else)."""

    kind: Kind
    permission_classes = [IsAuthenticated]

    def get_party_object(self):
        return selectors.get_for_party(self.kind.queryset(), self.kwargs["pk"], self.request.user)


class _DetailView(_PartyObjectMixin, GenericAPIView):
    def get_serializer_class(self):
        return self.kind.detail_serializer

    def get(self, request, pk):
        obj, role = self.get_party_object()
        return Response(self.kind.detail_serializer(obj, context={"role": role}).data)


class _TransitionView(_PartyObjectMixin, GenericAPIView):
    def get_serializer_class(self):
        return self.kind.transition_serializer

    def post(self, request, pk):
        obj, role = self.get_party_object()
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.change_status(
            self.kind.machine,
            obj,
            actor=request.user,
            role=role,
            to_status=data.validated_data["status"],
            note=data.validated_data.get("note", ""),
        )
        fresh = self.kind.queryset().get(pk=obj.pk)
        return Response(self.kind.detail_serializer(fresh, context={"role": role}).data)


class _HistoryView(_PartyObjectMixin, GenericAPIView):
    pagination_class = None

    def get_serializer_class(self):
        return self.kind.history_serializer

    def get(self, request, pk):
        obj, _ = self.get_party_object()
        rows = obj.history.select_related("actor")
        serializer = self.kind.history_serializer(
            rows, many=True, context={"applicant_user_id": obj.job_seeker.user_id}
        )
        return Response(serializer.data)


def _create_response(kind: Kind, request, post_id):
    data = kind.create_serializer(data=request.data)
    data.is_valid(raise_exception=True)
    if kind is APPLICATIONS:
        obj = services.submit_application(
            user=request.user,
            post_id=post_id,
            cover_letter=data.validated_data.get("cover_letter", ""),
        )
    else:
        obj = services.submit_proposal(user=request.user, post_id=post_id, **data.validated_data)
    fresh = kind.queryset().get(pk=obj.pk)
    return Response(
        kind.detail_serializer(fresh, context={"role": services.APPLICANT}).data,
        status=status.HTTP_201_CREATED,
    )


class MyApplicationsView(_MineView):
    kind = APPLICATIONS


class PostApplicationsView(_ForPostView):
    kind = APPLICATIONS

    def post(self, request, post_id):
        return _create_response(self.kind, request, post_id)


class ApplicationDetailView(_DetailView):
    kind = APPLICATIONS


class ApplicationTransitionView(_TransitionView):
    kind = APPLICATIONS


class ApplicationHistoryView(_HistoryView):
    kind = APPLICATIONS


class MyProposalsView(_MineView):
    kind = PROPOSALS


class PostProposalsView(_ForPostView):
    kind = PROPOSALS

    def post(self, request, post_id):
        return _create_response(self.kind, request, post_id)


class ProposalDetailView(_DetailView):
    kind = PROPOSALS


class ProposalTransitionView(_TransitionView):
    kind = PROPOSALS


class ProposalHistoryView(_HistoryView):
    kind = PROPOSALS

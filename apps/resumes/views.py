from django.db.models import Prefetch
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.common.exceptions import Conflict
from apps.profiles.permissions import IsJobSeeker

from . import serializers as sz
from . import services
from .models import (
    Certificate,
    DesiredJobTitle,
    Education,
    Language,
    PortfolioItem,
    Resume,
    ResumeSkill,
    WorkExperience,
)


def resume_queryset():
    """One resume with every section loaded in a fixed, small number of queries."""
    return Resume.objects.select_related("job_seeker").prefetch_related(
        Prefetch("desired_job_titles", DesiredJobTitle.objects.select_related("job_title")),
        Prefetch("resume_skills", ResumeSkill.objects.select_related("skill")),
        "educations",
        "work_experiences",
        "languages",
        "certificates",
        "portfolio_items",
    )


class _OwnResumeMixin:
    """Every resume endpoint is scoped to the caller's own resume: there is no resume id in any
    URL, so there is nothing to tamper with and no way to reach someone else's data."""

    permission_classes = [IsJobSeeker]

    def get_resume(self):
        if not hasattr(self, "_resume"):
            try:
                self._resume = Resume.objects.get(job_seeker=self.request.user.job_seeker_profile)
            except Resume.DoesNotExist as exc:
                raise NotFound("Create your resume first.") from exc
        return self._resume


class ResumeView(_OwnResumeMixin, GenericAPIView):
    """GET / POST (create once) / PATCH the caller's main resume."""

    serializer_class = sz.ResumeSerializer

    def _fresh(self, pk):
        return resume_queryset().get(pk=pk)

    def get(self, request):
        resume = resume_queryset().filter(job_seeker=request.user.job_seeker_profile).first()
        if resume is None:
            raise NotFound("Create your resume first.")
        return Response(self.get_serializer(resume).data)

    def post(self, request):
        profile = request.user.job_seeker_profile
        if Resume.objects.filter(job_seeker=profile).exists():
            raise Conflict("You already have a resume.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = serializer.save(job_seeker=profile)
        return Response(
            self.get_serializer(self._fresh(resume.pk)).data, status=status.HTTP_201_CREATED
        )

    def patch(self, request):
        resume = self.get_resume()
        serializer = self.get_serializer(resume, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(self._fresh(resume.pk)).data)


class _SectionViewSet(_OwnResumeMixin, viewsets.ModelViewSet):
    """Generic CRUD for one resume section. Lists are small and returned unpaginated."""

    pagination_class = None
    filter_backends: list = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    model = None
    relation = ""  # key in services.MAX_ITEMS
    select_related: tuple = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        qs = self.model.objects.filter(resume=self.get_resume())
        return qs.select_related(*self.select_related) if self.select_related else qs

    def perform_create(self, serializer):
        resume = self.get_resume()
        services.check_item_limit(resume, self.relation)
        serializer.save(resume=resume)


class EducationViewSet(_SectionViewSet):
    model, relation, serializer_class = Education, "educations", sz.EducationSerializer


class WorkExperienceViewSet(_SectionViewSet):
    model, relation = WorkExperience, "work_experiences"
    serializer_class = sz.WorkExperienceSerializer


class ResumeSkillViewSet(_SectionViewSet):
    model, relation = ResumeSkill, "resume_skills"
    serializer_class = sz.ResumeSkillSerializer
    select_related = ("skill",)


class DesiredJobTitleViewSet(_SectionViewSet):
    model, relation = DesiredJobTitle, "desired_job_titles"
    serializer_class = sz.DesiredJobTitleSerializer
    select_related = ("job_title",)
    http_method_names = ["get", "post", "delete", "head", "options"]


class LanguageViewSet(_SectionViewSet):
    model, relation, serializer_class = Language, "languages", sz.LanguageSerializer


class CertificateViewSet(_SectionViewSet):
    model, relation, serializer_class = Certificate, "certificates", sz.CertificateSerializer


class PortfolioItemViewSet(_SectionViewSet):
    model, relation = PortfolioItem, "portfolio_items"
    serializer_class = sz.PortfolioItemSerializer


class _IgnoreClientContentNegotiation(BaseContentNegotiation):
    """Lets an <img>/fetch with `Accept: image/*` reach the photo endpoint."""

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class ResumePhotoView(_OwnResumeMixin, GenericAPIView):
    """PUT multipart `photo` / GET (owner only) / DELETE. The photo is private to its owner;
    access for employers is decided together with applications (Phase 6)."""

    serializer_class = sz.PhotoUploadSerializer
    parser_classes = [MultiPartParser]
    content_negotiation_class = _IgnoreClientContentNegotiation

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = self.get_resume()
        services.set_photo(resume, serializer.validated_data["photo"])
        return Response({"has_photo": True})

    def get(self, request):
        resume = self.get_resume()
        if not resume.photo:
            raise NotFound("No photo uploaded.")
        response = FileResponse(resume.photo.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def delete(self, request):
        services.remove_photo(self.get_resume())
        return Response(status=status.HTTP_204_NO_CONTENT)

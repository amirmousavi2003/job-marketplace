from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import Conflict

from .serializers import EmployerProfileSerializer, JobSeekerProfileSerializer


class _MyProfileView(GenericAPIView):
    """GET / POST (create once) / PATCH the authenticated user's own profile."""

    permission_classes = [IsAuthenticated]
    profile_attr: str

    def get_object(self):
        try:
            return getattr(self.request.user, self.profile_attr)
        except ObjectDoesNotExist as exc:
            raise NotFound("Profile does not exist yet.") from exc

    def get(self, request):
        return Response(self.get_serializer(self.get_object()).data)

    def post(self, request):
        if hasattr(request.user, self.profile_attr):
            raise Conflict("Profile already exists.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class JobSeekerProfileView(_MyProfileView):
    serializer_class = JobSeekerProfileSerializer
    profile_attr = "job_seeker_profile"


class EmployerProfileView(_MyProfileView):
    serializer_class = EmployerProfileSerializer
    profile_attr = "employer_profile"

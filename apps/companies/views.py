from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.profiles.permissions import IsEmployer

from . import selectors, services
from .models import CompanyMembership
from .serializers import AddMemberSerializer, CompanySerializer, MembershipSerializer


class IsCompanyOwnerOrReadOnly(BasePermission):
    """Queryset already limits objects to the caller's companies; writes need OWNER."""

    message = "Only the company owner can do this."

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.my_role == CompanyMembership.Role.OWNER


class _CompanyScopedMixin:
    permission_classes = [IsEmployer]

    def my_companies(self):
        return selectors.companies_for_employer(self.request.user.employer_profile)


class CompanyListCreateView(_CompanyScopedMixin, ListCreateAPIView):
    serializer_class = CompanySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CompanySerializer.Meta.model.objects.none()
        return self.my_companies()

    def perform_create(self, serializer):
        company = services.create_company(
            employer=self.request.user.employer_profile, **serializer.validated_data
        )
        company.my_role = CompanyMembership.Role.OWNER
        serializer.instance = company


class CompanyDetailView(_CompanyScopedMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = CompanySerializer
    permission_classes = [IsEmployer, IsCompanyOwnerOrReadOnly]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CompanySerializer.Meta.model.objects.none()
        return self.my_companies()

    def perform_destroy(self, instance):
        services.deactivate_company(instance)


class _MembersBase(_CompanyScopedMixin):
    def get_company(self):
        return get_object_or_404(self.my_companies(), pk=self.kwargs["company_id"])


class CompanyMembersView(_MembersBase, GenericAPIView):
    serializer_class = MembershipSerializer

    def get(self, request, company_id):
        company = self.get_company()
        members = selectors.memberships_of(company).order_by("id")
        page = self.paginate_queryset(members)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def post(self, request, company_id):
        company = self.get_company()
        if company.my_role != CompanyMembership.Role.OWNER:
            raise PermissionDenied("Only the company owner can add members.")
        data = AddMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = services.add_member(company=company, email=data.validated_data["email"])
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class CompanyMemberDetailView(_MembersBase, GenericAPIView):
    serializer_class = MembershipSerializer
    http_method_names = ["delete", "options"]

    def delete(self, request, company_id, membership_id):
        company = self.get_company()
        membership = get_object_or_404(
            CompanyMembership.objects.select_related("employer"),
            pk=membership_id,
            company=company,
        )
        is_self = membership.employer_id == request.user.employer_profile.pk
        if company.my_role != CompanyMembership.Role.OWNER and not is_self:
            raise PermissionDenied("Only the owner can remove other members.")
        services.remove_member(membership)
        return Response(status=status.HTTP_204_NO_CONTENT)

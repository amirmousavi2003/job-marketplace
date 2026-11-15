from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.profiles.models import EmployerProfile

from .models import Company, CompanyMembership


@transaction.atomic
def create_company(*, employer, **data) -> Company:
    company = Company.objects.create(**data)
    CompanyMembership.objects.create(
        company=company, employer=employer, role=CompanyMembership.Role.OWNER
    )
    return company


def deactivate_company(company: Company) -> None:
    company.is_active = False
    company.save(update_fields=["is_active", "updated_at"])


@transaction.atomic
def add_member(*, company: Company, email: str) -> CompanyMembership:
    employer = (
        EmployerProfile.objects.select_related("user")
        .filter(user__email=email.strip().lower(), user__is_active=True)
        .first()
    )
    if employer is None:
        raise ValidationError({"email": ["No employer account found with this email."]})
    if CompanyMembership.objects.filter(company=company, employer=employer).exists():
        raise ValidationError({"email": ["This employer is already a member."]})
    return CompanyMembership.objects.create(company=company, employer=employer)


def remove_member(membership: CompanyMembership) -> None:
    if membership.role == CompanyMembership.Role.OWNER:
        raise ValidationError({"detail": "The company owner cannot be removed."})
    membership.delete()

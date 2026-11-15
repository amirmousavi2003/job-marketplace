from django.db.models import F

from .models import Company, CompanyMembership


def companies_for_employer(employer):
    """Active companies the employer belongs to, annotated with their role (my_role)."""
    return (
        Company.objects.filter(is_active=True, memberships__employer=employer)
        .annotate(my_role=F("memberships__role"))
        .order_by("name", "id")
    )


def memberships_of(company):
    return CompanyMembership.objects.filter(company=company).select_related("employer__user")

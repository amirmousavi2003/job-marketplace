from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.profiles.models import EmployerProfile


class Company(TimeStampedModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)  # soft delete: posts will PROTECT companies
    is_verified = models.BooleanField(default=False)  # set by admins only

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class CompanyMembership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MEMBER = "MEMBER", "Member"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE, related_name="company_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employer"], name="companies_unique_member_per_company"
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(role="OWNER"),
                name="companies_single_owner_per_company",
            ),
        ]

    def __str__(self):
        return f"{self.employer} @ {self.company} ({self.role})"

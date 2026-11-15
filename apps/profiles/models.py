from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class JobSeekerProfile(TimeStampedModel):
    """Identity of a person looking for work. The resume (Phase 4) hangs off this."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_seeker_profile"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class EmployerProfile(TimeStampedModel):
    """An employer: an individual or a person acting for one or more companies."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employer_profile"
    )
    display_name = models.CharField(max_length=150)
    about = models.TextField(blank=True)

    def __str__(self):
        return self.display_name

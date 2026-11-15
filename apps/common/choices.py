"""Enums shared across domains (resume preferences now, job requirements later)."""

from django.db import models


class ExperienceLevel(models.TextChoices):
    NO_EXPERIENCE = "NO_EXPERIENCE", "No experience"
    JUNIOR = "JUNIOR", "Junior (under 2 years)"
    MID = "MID", "Mid-level (2 to 5 years)"
    SENIOR = "SENIOR", "Senior (5+ years)"


class WorkMode(models.TextChoices):
    ON_SITE = "ON_SITE", "On-site"
    REMOTE = "REMOTE", "Remote"
    HYBRID = "HYBRID", "Hybrid"

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


class DegreeLevel(models.TextChoices):
    BELOW_DIPLOMA = "BELOW_DIPLOMA", "Below diploma"
    DIPLOMA = "DIPLOMA", "Diploma"
    ASSOCIATE = "ASSOCIATE", "Associate (Kardani)"
    BACHELOR = "BACHELOR", "Bachelor"
    MASTER = "MASTER", "Master"
    DOCTORATE = "DOCTORATE", "Doctorate"


class SkillLevel(models.TextChoices):
    BEGINNER = "BEGINNER", "Beginner"
    INTERMEDIATE = "INTERMEDIATE", "Intermediate"
    ADVANCED = "ADVANCED", "Advanced"
    EXPERT = "EXPERT", "Expert"

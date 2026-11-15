"""Central catalogue: skills, job titles, categories, plus moderated user suggestions.

Design: every searchable term of a skill / job title (its names AND its aliases) is one row
in an alias table with a globally unique `normalized_text`. So a term can never point to two
entries, and Arabic/Persian letter variants, ZWNJ and digits cannot create near-duplicates.
"""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.common.text import normalize_text


class CatalogueEntry(TimeStampedModel):
    """Abstract base for Skill and JobTitle."""

    name_fa = models.CharField(max_length=100, blank=True)
    name_en = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=~Q(name_fa="") | ~Q(name_en=""),
                name="%(app_label)s_%(class)s_has_a_name",
            )
        ]

    @property
    def display_name(self) -> str:
        return self.name_fa or self.name_en

    def __str__(self):
        return self.display_name

    def _names(self):
        return [n.strip() for n in (self.name_fa, self.name_en) if n and n.strip()]

    def clean(self):
        self.name_fa = (self.name_fa or "").strip()
        self.name_en = (self.name_en or "").strip()
        if not self._names():
            raise ValidationError("At least one of name_fa / name_en is required.")
        alias_model = self._meta.get_field("aliases").related_model
        for name in self._names():
            clash = alias_model.objects.filter(normalized_text=normalize_text(name))
            if self.pk:
                clash = clash.exclude(**{self._alias_fk: self})
            if clash.exists():
                raise ValidationError(f"'{name}' already exists in the catalogue.")

    def save(self, *args, **kwargs):
        self.name_fa = (self.name_fa or "").strip()
        self.name_en = (self.name_en or "").strip()
        super().save(*args, **kwargs)
        self._sync_name_terms()

    def _sync_name_terms(self):
        """Keep one alias row (is_name=True) per name so names are searchable and unique."""
        wanted = {normalize_text(n): n for n in self._names()}
        for term in self.aliases.filter(is_name=True):
            if term.normalized_text not in wanted:
                term.delete()
        for key, text in wanted.items():
            term, created = self.aliases.get_or_create(
                normalized_text=key, defaults={"text": text, "is_name": True}
            )
            if not created and not term.is_name:
                term.is_name = True
                term.save(update_fields=["is_name"])


class CatalogueTerm(models.Model):
    """Abstract alias row. `normalized_text` is unique per catalogue."""

    text = models.CharField(max_length=100)
    normalized_text = models.CharField(max_length=100, unique=True, editable=False)
    is_name = models.BooleanField(default=False, help_text="Auto-managed copy of a name.")

    class Meta:
        abstract = True

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        self.text = (self.text or "").strip()
        self.normalized_text = normalize_text(self.text)
        super().save(*args, **kwargs)

    def clean(self):
        self.text = (self.text or "").strip()
        self.normalized_text = normalize_text(self.text)
        if not self.normalized_text:
            raise ValidationError("Text is required.")
        clash = type(self).objects.filter(normalized_text=self.normalized_text)
        if self.pk:
            clash = clash.exclude(pk=self.pk)
        if clash.exists():
            raise ValidationError("This term already exists in the catalogue.")


class Skill(CatalogueEntry):
    _alias_fk = "skill"

    class Meta(CatalogueEntry.Meta):
        ordering = ["id"]


class SkillAlias(CatalogueTerm):
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")

    class Meta:
        verbose_name_plural = "skill aliases"
        indexes = [
            GinIndex(
                fields=["normalized_text"],
                name="skills_skillalias_trgm",
                opclasses=["gin_trgm_ops"],
            )
        ]


class JobTitle(CatalogueEntry):
    _alias_fk = "job_title"

    class Meta(CatalogueEntry.Meta):
        ordering = ["id"]


class JobTitleAlias(CatalogueTerm):
    job_title = models.ForeignKey(JobTitle, on_delete=models.CASCADE, related_name="aliases")

    class Meta:
        verbose_name_plural = "job title aliases"
        indexes = [
            GinIndex(
                fields=["normalized_text"],
                name="skills_jobtitlealias_trgm",
                opclasses=["gin_trgm_ops"],
            )
        ]


class JobCategory(TimeStampedModel):
    """Two-level category tree (top level + one sub level)."""

    name_fa = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    slug = models.SlugField(max_length=100, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name_plural = "job categories"
        constraints = [
            models.CheckConstraint(
                condition=~Q(parent=models.F("id")), name="skills_category_not_own_parent"
            )
        ]

    def __str__(self):
        return self.name_fa

    def clean(self):
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError("A category cannot be its own parent.")
            if self.parent.parent_id:
                raise ValidationError("Categories support only two levels.")
            if self.pk and self.children.exists():
                raise ValidationError("A category with children cannot become a sub-category.")


class SuggestionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Suggestion(TimeStampedModel):
    """Abstract user-submitted catalogue suggestion awaiting admin moderation."""

    suggested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )
    text = models.CharField(max_length=100)
    normalized_text = models.CharField(max_length=100, editable=False)
    status = models.CharField(
        max_length=10, choices=SuggestionStatus.choices, default=SuggestionStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_%(class)ss",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        abstract = True
        ordering = ["-id"]
        constraints = [
            # Only one pending suggestion per term, no matter who suggested it.
            models.UniqueConstraint(
                fields=["normalized_text"],
                condition=Q(status="PENDING"),
                name="%(app_label)s_%(class)s_one_pending_per_term",
            ),
        ]

    def __str__(self):
        return f"{self.text} [{self.status}]"

    def save(self, *args, **kwargs):
        self.normalized_text = normalize_text(self.text)
        super().save(*args, **kwargs)


class SkillSuggestion(Suggestion):
    resulting_skill = models.ForeignKey(
        Skill, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )


class JobTitleSuggestion(Suggestion):
    resulting_job_title = models.ForeignKey(
        JobTitle, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

"""Catalogue business rules: duplicate-free creation, aliases, and suggestion moderation."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.exceptions import Conflict
from apps.common.text import normalize_text

from .models import (
    JobTitle,
    JobTitleAlias,
    JobTitleSuggestion,
    Skill,
    SkillAlias,
    SkillSuggestion,
    SuggestionStatus,
)

MAX_PENDING_SUGGESTIONS_PER_USER = 10


@dataclass(frozen=True)
class Kind:
    """Describes one catalogue (skills or job titles) so the logic is written once."""

    entry: type
    alias: type
    suggestion: type
    fk: str  # name of the FK from alias to entry
    result_field: str  # suggestion field pointing to the created/matched entry


SKILL = Kind(Skill, SkillAlias, SkillSuggestion, "skill", "resulting_skill")
JOB_TITLE = Kind(JobTitle, JobTitleAlias, JobTitleSuggestion, "job_title", "resulting_job_title")


def clean_term(text: str, field: str = "text") -> str:
    """Normalize a user-typed term and reject junk. Returns the normalized form."""
    normalized = normalize_text(text)
    if len(normalized) < 2 or not any(ch.isalpha() for ch in normalized):
        raise ValidationError({field: ["Enter at least 2 characters including a letter."]})
    return normalized


def find_entry(kind: Kind, text: str):
    term = (
        kind.alias.objects.filter(normalized_text=normalize_text(text))
        .select_related(kind.fk)
        .first()
    )
    return getattr(term, kind.fk) if term else None


def _assert_terms_free(kind: Kind, terms, exclude_entry=None):
    for text in terms:
        owner = find_entry(kind, text)
        if owner is not None and owner != exclude_entry:
            raise ValidationError(
                {
                    "text": [
                        f"'{text}' already exists in the catalogue as '{owner}' (id {owner.pk})."
                    ]
                }
            )


@transaction.atomic
def create_entry(kind: Kind, *, name_fa="", name_en="", aliases=()):
    name_fa, name_en = (name_fa or "").strip(), (name_en or "").strip()
    if not (name_fa or name_en):
        raise ValidationError({"name_fa": ["Provide name_fa or name_en."]})
    extra = [a.strip() for a in aliases if a and a.strip()]
    _assert_terms_free(kind, [n for n in (name_fa, name_en) if n] + extra)
    entry = kind.entry.objects.create(name_fa=name_fa, name_en=name_en)
    for text in extra:
        if not kind.alias.objects.filter(normalized_text=normalize_text(text)).exists():
            kind.alias.objects.create(**{kind.fk: entry}, text=text)
    return entry


@transaction.atomic
def add_alias(kind: Kind, entry, text: str):
    clean_term(text)
    _assert_terms_free(kind, [text], exclude_entry=entry)
    term, _ = kind.alias.objects.get_or_create(
        normalized_text=normalize_text(text), defaults={"text": text.strip(), kind.fk: entry}
    )
    return term


def submit_suggestion(kind: Kind, *, user, text: str):
    text = (text or "").strip()
    normalized = clean_term(text)
    existing = find_entry(kind, text)
    if existing is not None:
        raise ValidationError(
            {"text": [f"Already in the catalogue as '{existing}' (id {existing.pk}). Select it."]}
        )
    if kind.suggestion.objects.filter(normalized_text=normalized, status="PENDING").exists():
        raise Conflict("A suggestion for this term is already waiting for review.")
    pending = kind.suggestion.objects.filter(suggested_by=user, status="PENDING").count()
    if pending >= MAX_PENDING_SUGGESTIONS_PER_USER:
        raise ValidationError(
            {"detail": f"You already have {pending} pending suggestions. Wait for a review."}
        )
    try:
        with transaction.atomic():
            return kind.suggestion.objects.create(suggested_by=user, text=text)
    except IntegrityError as exc:  # lost a race against an identical suggestion
        raise Conflict("A suggestion for this term is already waiting for review.") from exc


def _looks_persian(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


@transaction.atomic
def approve_suggestion(
    kind: Kind, suggestion, *, reviewer, existing=None, name_fa="", name_en="", aliases=(), note=""
):
    suggestion = kind.suggestion.objects.select_for_update().get(pk=suggestion.pk)
    if suggestion.status != SuggestionStatus.PENDING:
        raise Conflict("This suggestion was already reviewed.")

    if existing is not None:
        add_alias(kind, existing, suggestion.text)
        entry = existing
    else:
        if not (name_fa or name_en):
            if _looks_persian(suggestion.text):
                name_fa = suggestion.text
            else:
                name_en = suggestion.text
        entry = create_entry(kind, name_fa=name_fa, name_en=name_en, aliases=aliases)
        if not find_entry(kind, suggestion.text):
            add_alias(kind, entry, suggestion.text)

    suggestion.status = SuggestionStatus.APPROVED
    suggestion.reviewed_by = reviewer
    suggestion.reviewed_at = timezone.now()
    suggestion.resolution_note = note
    setattr(suggestion, kind.result_field, entry)
    suggestion.save()
    return suggestion


@transaction.atomic
def reject_suggestion(kind: Kind, suggestion, *, reviewer, note: str):
    suggestion = kind.suggestion.objects.select_for_update().get(pk=suggestion.pk)
    if suggestion.status != SuggestionStatus.PENDING:
        raise Conflict("This suggestion was already reviewed.")
    if len((note or "").strip()) < 3:
        raise ValidationError({"note": ["A rejection reason is required."]})
    suggestion.status = SuggestionStatus.REJECTED
    suggestion.reviewed_by = reviewer
    suggestion.reviewed_at = timezone.now()
    suggestion.resolution_note = note.strip()
    suggestion.save()
    return suggestion

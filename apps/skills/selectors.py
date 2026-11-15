from django.db.models import Case, IntegerField, Value, When

from apps.common.text import normalize_text


def search_catalogue(kind, query: str):
    """Active entries whose any term (name or alias) contains the normalized query.
    Exact matches first, then prefix matches, then the rest."""
    qs = kind.entry.objects.filter(is_active=True)
    normalized = normalize_text(query or "")
    if not normalized:
        return qs.order_by("id")
    terms = kind.alias.objects.filter(normalized_text__contains=normalized)
    matched_ids = terms.values_list(kind.fk + "_id", flat=True)
    exact = terms.filter(normalized_text=normalized).values_list(kind.fk + "_id", flat=True)
    prefix = terms.filter(normalized_text__startswith=normalized).values_list(
        kind.fk + "_id", flat=True
    )
    return (
        qs.filter(pk__in=matched_ids)
        .annotate(
            rank=Case(
                When(pk__in=exact, then=Value(0)),
                When(pk__in=prefix, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("rank", "id")
    )

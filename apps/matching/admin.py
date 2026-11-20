from django.contrib import admin

from .models import AIMatch, EmbeddingCache


@admin.register(AIMatch)
class AIMatchAdmin(admin.ModelAdmin):
    """Derived data about private resumes: view only."""

    list_display = (
        "id",
        "job_seeker",
        "job_post",
        "score",
        "provider",
        "semantic_used",
        "computed_at",
    )
    list_filter = ("provider", "semantic_used")
    exclude = ("factors", "explanation")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmbeddingCache)
class EmbeddingCacheAdmin(admin.ModelAdmin):
    list_display = ("provider", "model", "text_hash", "created_at")
    exclude = ("vector",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

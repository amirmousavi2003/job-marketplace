from django.contrib import admin

from .models import ModerationHistory


@admin.register(ModerationHistory)
class ModerationHistoryAdmin(admin.ModelAdmin):
    """Append-only audit log: view only."""

    list_display = ("job_post", "from_status", "to_status", "actor", "created_at")
    list_filter = ("to_status",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

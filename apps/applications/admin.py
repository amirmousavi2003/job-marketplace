from django.contrib import admin

from .models import (
    Application,
    ApplicationStatusHistory,
    ProjectProposal,
    ProjectProposalStatusHistory,
)


class _ReadOnly(admin.ModelAdmin):
    """Applicants' data is private. Staff can look, nobody edits through the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(_ReadOnly):
    list_display = ("id", "job_post", "job_seeker", "status", "created_at")
    list_filter = ("status",)
    exclude = ("resume_snapshot",)


@admin.register(ProjectProposal)
class ProjectProposalAdmin(_ReadOnly):
    list_display = ("id", "job_post", "job_seeker", "proposed_price", "status", "created_at")
    list_filter = ("status",)


admin.site.register(ApplicationStatusHistory, _ReadOnly)
admin.site.register(ProjectProposalStatusHistory, _ReadOnly)

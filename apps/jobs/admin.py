from django.contrib import admin

from .models import EmploymentDetail, JobPost, JobPostSkill, ProjectDetail


class _ReadOnlyInline(admin.StackedInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class EmploymentInline(_ReadOnlyInline):
    model = EmploymentDetail


class ProjectInline(_ReadOnlyInline):
    model = ProjectDetail


class SkillInline(_ReadOnlyInline):
    model = JobPostSkill


@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    """Read-only overview. Moderation goes through the API/service so history is always written."""

    list_display = ("id", "title", "post_type", "moderation_status", "lifecycle_status", "employer")
    list_filter = ("post_type", "moderation_status", "lifecycle_status")
    search_fields = ("title", "employer__display_name", "employer__user__email")
    inlines = [EmploymentInline, ProjectInline, SkillInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

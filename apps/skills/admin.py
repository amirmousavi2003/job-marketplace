from django.contrib import admin

from .models import (
    JobCategory,
    JobTitle,
    JobTitleAlias,
    JobTitleSuggestion,
    Skill,
    SkillAlias,
    SkillSuggestion,
)


class SkillAliasInline(admin.TabularInline):
    model = SkillAlias
    extra = 1
    exclude = ("is_name",)


class JobTitleAliasInline(admin.TabularInline):
    model = JobTitleAlias
    extra = 1
    exclude = ("is_name",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("id", "name_fa", "name_en", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_fa", "name_en", "aliases__text")
    inlines = [SkillAliasInline]


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ("id", "name_fa", "name_en", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_fa", "name_en", "aliases__text")
    inlines = [JobTitleAliasInline]


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_fa", "name_en", "slug", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name_en",)}


class _ReadOnlySuggestionAdmin(admin.ModelAdmin):
    """Reviews go through the moderation API/service so rules and notes are enforced."""

    list_display = ("text", "status", "suggested_by", "reviewed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("text",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(SkillSuggestion, _ReadOnlySuggestionAdmin)
admin.site.register(JobTitleSuggestion, _ReadOnlySuggestionAdmin)

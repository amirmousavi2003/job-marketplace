from django.contrib import admin

from .models import Company, CompanyMembership


class MembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    raw_id_fields = ("employer",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "is_verified", "created_at")
    list_filter = ("is_active", "is_verified")
    search_fields = ("name",)
    inlines = [MembershipInline]

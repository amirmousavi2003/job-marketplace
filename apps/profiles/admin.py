from django.contrib import admin

from .models import EmployerProfile, JobSeekerProfile


@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "user")
    search_fields = ("first_name", "last_name", "user__email")
    raw_id_fields = ("user",)


@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "user")
    search_fields = ("display_name", "user__email")
    raw_id_fields = ("user",)

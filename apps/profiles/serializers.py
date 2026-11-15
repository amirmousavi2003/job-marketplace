from rest_framework import serializers

from .models import EmployerProfile, JobSeekerProfile


class JobSeekerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSeekerProfile
        fields = ("id", "first_name", "last_name", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class EmployerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployerProfile
        fields = ("id", "display_name", "about", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

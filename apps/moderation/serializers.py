from django.db.models import Count, Q
from rest_framework import serializers

from apps.jobs.models import JobPost, ModerationStatus
from apps.jobs.serializers import OwnerJobPostSerializer

from .models import ModerationHistory


class ModerationHistorySerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = ModerationHistory
        fields = ("id", "from_status", "to_status", "actor_email", "note", "created_at")
        read_only_fields = fields


class AdminJobPostListSerializer(serializers.ModelSerializer):
    employer_name = serializers.CharField(source="employer.display_name", read_only=True)
    employer_email = serializers.EmailField(source="employer.user.email", read_only=True)

    class Meta:
        model = JobPost
        fields = (
            "id",
            "post_type",
            "title",
            "moderation_status",
            "lifecycle_status",
            "employer_name",
            "employer_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AdminJobPostSerializer(OwnerJobPostSerializer):
    """Everything a reviewer needs: the post, who posted it, and the full history."""

    employer_info = serializers.SerializerMethodField()
    moderation_history = ModerationHistorySerializer(many=True, read_only=True)

    class Meta(OwnerJobPostSerializer.Meta):
        fields = (*OwnerJobPostSerializer.Meta.fields, "employer_info", "moderation_history")
        read_only_fields = fields

    def get_employer_info(self, obj) -> dict:
        employer = obj.employer
        counts = JobPost.objects.filter(employer=employer).aggregate(
            total=Count("id"),
            approved=Count("id", filter=Q(moderation_status=ModerationStatus.APPROVED)),
            rejected=Count("id", filter=Q(moderation_status=ModerationStatus.REJECTED)),
        )
        user = employer.user
        return {
            "id": employer.pk,
            "display_name": employer.display_name,
            "about": employer.about,
            "email": user.email,
            "phone": user.phone,
            "joined": user.date_joined,
            "is_active": user.is_active,
            "posts_total": counts["total"],
            "posts_approved": counts["approved"],
            "posts_rejected": counts["rejected"],
        }


class JobApproveSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class JobRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=1000)

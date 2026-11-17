from rest_framework import serializers

from .models import JobCategory, JobTitle, JobTitleSuggestion, Skill, SkillSuggestion


class JobCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCategory
        fields = ("id", "name_fa", "name_en", "slug", "parent")


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ("id", "name_fa", "name_en")


class JobTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobTitle
        fields = ("id", "name_fa", "name_en")


class SuggestionCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=100, trim_whitespace=True)


class _SuggestionBase(serializers.ModelSerializer):
    """What the person who suggested sees: no reviewer identity."""

    class Meta:
        fields = ("id", "text", "status", "resolution_note", "created_at", "resulting")
        read_only_fields = fields


class SkillSuggestionSerializer(_SuggestionBase):
    resulting = SkillSerializer(source="resulting_skill", read_only=True)

    class Meta(_SuggestionBase.Meta):
        model = SkillSuggestion


class JobTitleSuggestionSerializer(_SuggestionBase):
    resulting = JobTitleSerializer(source="resulting_job_title", read_only=True)

    class Meta(_SuggestionBase.Meta):
        model = JobTitleSuggestion


class _AdminSuggestionBase(serializers.ModelSerializer):
    suggested_by_email = serializers.EmailField(source="suggested_by.email", read_only=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True)

    class Meta:
        fields = (
            "id",
            "text",
            "status",
            "suggested_by_email",
            "reviewed_by_email",
            "reviewed_at",
            "resolution_note",
            "created_at",
            "resulting",
        )
        read_only_fields = fields


class AdminSkillSuggestionSerializer(_AdminSuggestionBase):
    resulting = SkillSerializer(source="resulting_skill", read_only=True)

    class Meta(_AdminSuggestionBase.Meta):
        model = SkillSuggestion


class AdminJobTitleSuggestionSerializer(_AdminSuggestionBase):
    resulting = JobTitleSerializer(source="resulting_job_title", read_only=True)

    class Meta(_AdminSuggestionBase.Meta):
        model = JobTitleSuggestion


class SuggestionApproveSerializer(serializers.Serializer):
    """Either map to an existing entry (existing_id) or create a new one (names/aliases)."""

    existing_id = serializers.IntegerField(required=False)
    name_fa = serializers.CharField(required=False, allow_blank=True, max_length=100)
    name_en = serializers.CharField(required=False, allow_blank=True, max_length=100)
    aliases = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=20
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if attrs.get("existing_id") and (
            attrs.get("name_fa") or attrs.get("name_en") or attrs.get("aliases")
        ):
            raise serializers.ValidationError(
                "Use either existing_id or new names/aliases, not both."
            )
        return attrs


class SuggestionRejectSerializer(serializers.Serializer):
    note = serializers.CharField(min_length=3, max_length=1000)

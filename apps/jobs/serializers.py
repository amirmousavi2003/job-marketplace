from django.utils import timezone
from rest_framework import serializers

from apps.companies.models import Company
from apps.companies.selectors import companies_for_employer
from apps.skills.models import JobCategory, Skill
from apps.skills.serializers import JobCategorySerializer

from . import selectors, services
from .models import EmploymentDetail, JobPost, JobPostSkill, PostType, ProjectDetail

MAX_SKILLS = 20


# ------------------------------------------------------------------ details & skills
class JobPostSkillSerializer(serializers.ModelSerializer):
    skill = serializers.PrimaryKeyRelatedField(queryset=Skill.objects.filter(is_active=True))
    skill_name_fa = serializers.CharField(source="skill.name_fa", read_only=True)
    skill_name_en = serializers.CharField(source="skill.name_en", read_only=True)

    class Meta:
        model = JobPostSkill
        fields = ("skill", "skill_name_fa", "skill_name_en", "is_required", "minimum_level")


def _check_range(values: dict, low: str, high: str, label: str):
    if values.get(low) is not None and values.get(high) is not None and values[high] < values[low]:
        raise serializers.ValidationError(
            {high: [f"Maximum {label} cannot be lower than minimum."]}
        )


class EmploymentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmploymentDetail
        fields = (
            "employment_type",
            "salary_min",
            "salary_max",
            "required_experience_level",
            "required_education",
            "additional_qualifications",
            "other_conditions",
        )
        extra_kwargs = {
            "salary_min": {"min_value": 1},
            "salary_max": {"min_value": 1},
            "additional_qualifications": {"max_length": 3000},
            "other_conditions": {"max_length": 3000},
        }

    def validate(self, attrs):
        _check_range(attrs, "salary_min", "salary_max", "salary")
        return attrs


class ProjectDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDetail
        fields = (
            "budget_min",
            "budget_max",
            "currency",
            "expected_duration_days",
            "deadline",
            "expected_deliverables",
            "additional_requirements",
        )
        extra_kwargs = {
            "budget_min": {"min_value": 1},
            "budget_max": {"min_value": 1},
            "expected_duration_days": {"min_value": 1},
            "expected_deliverables": {"max_length": 3000},
            "additional_requirements": {"max_length": 3000},
        }

    def validate_deadline(self, value):
        if value and value <= timezone.localdate():
            raise serializers.ValidationError("Deadline must be in the future.")
        return value

    def validate(self, attrs):
        _check_range(attrs, "budget_min", "budget_max", "budget")
        return attrs


# ------------------------------------------------------------------ write side
class _PostWriteBase(serializers.ModelSerializer):
    """Input only. Owner, type, status and dates are never accepted from the client:
    unknown / read-only keys in the body are ignored."""

    post_type: str  # set by subclasses
    detail_key: str
    detail_serializer: type[serializers.ModelSerializer]
    other_key: str

    category = serializers.PrimaryKeyRelatedField(
        queryset=JobCategory.objects.filter(is_active=True)
    )
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(is_active=True), required=False, allow_null=True
    )
    skills = JobPostSkillSerializer(many=True, required=False)

    class Meta:
        model = JobPost
        fields = (
            "title",
            "description",
            "category",
            "province",
            "city",
            "work_mode",
            "company",
            "duration_days",
            "skills",
        )
        extra_kwargs = {
            "title": {"min_length": 5},
            "description": {"min_length": 20, "max_length": 10000},
            "duration_days": {"min_value": 1, "max_value": 90},
            "province": {"required": False, "allow_null": True},
            "city": {"required": False, "allow_null": True},
        }

    def validate_company(self, company):
        if company is not None:
            mine = companies_for_employer(self.context["request"].user.employer_profile)
            if not mine.filter(pk=company.pk).exists():
                raise serializers.ValidationError("You are not a member of this company.")
        return company

    def validate_skills(self, items):
        if len(items) > MAX_SKILLS:
            raise serializers.ValidationError(f"At most {MAX_SKILLS} skills.")
        ids = [item["skill"].pk for item in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate skills.")
        return items

    def validate(self, attrs):
        if self.other_key in self.initial_data:
            raise serializers.ValidationError(
                {self.other_key: [f"Not allowed for {self.post_type.lower()} posts."]}
            )
        instance = self.instance
        if attrs.get("city") is not None and "province" not in attrs:
            attrs["province"] = attrs["city"].province
        city = attrs["city"] if "city" in attrs else (instance.city if instance else None)
        province = (
            attrs["province"] if "province" in attrs else (instance.province if instance else None)
        )
        if city is not None:
            if province is not None and province.pk != city.province_id:
                raise serializers.ValidationError(
                    {"city": ["City does not belong to the selected province."]}
                )
            attrs["province"] = province = city.province
        work_mode = attrs.get("work_mode", instance.work_mode if instance else None)
        if work_mode in ("ON_SITE", "HYBRID") and province is None:
            raise serializers.ValidationError(
                {"province": ["Province is required for on-site and hybrid work."]}
            )
        self._check_merged_detail(attrs)
        return attrs

    def _check_merged_detail(self, attrs):
        """On PATCH, re-check min/max using stored values for fields the client did not send."""
        sent = attrs.get(self.detail_key)
        if not (self.instance and sent):
            return
        stored = getattr(self.instance, services.DETAIL_RELATION[self.post_type])
        merged = {name: getattr(stored, name) for name in self.detail_serializer.Meta.fields}
        merged.update(sent)
        if self.post_type == PostType.EMPLOYMENT:
            _check_range(merged, "salary_min", "salary_max", "salary")
        else:
            _check_range(merged, "budget_min", "budget_max", "budget")

    def _split(self, validated: dict):
        data = dict(validated)
        detail = data.pop(self.detail_key, None)
        skills = data.pop("skills", None)
        return data, detail, skills

    def create(self, validated_data):
        data, detail, skills = self._split(validated_data)
        return services.create_job_post(
            employer=self.context["request"].user.employer_profile,
            post_type=self.post_type,
            data=data,
            detail=detail,
            skills=skills or [],
        )

    def update(self, instance, validated_data):
        data, detail, skills = self._split(validated_data)
        return services.update_job_post(
            instance, actor=self.context["request"].user, data=data, detail=detail, skills=skills
        )


class EmploymentPostWriteSerializer(_PostWriteBase):
    post_type = PostType.EMPLOYMENT
    detail_key, other_key = "employment", "project"
    detail_serializer = EmploymentDetailSerializer
    employment = EmploymentDetailSerializer()

    class Meta(_PostWriteBase.Meta):
        fields = (*_PostWriteBase.Meta.fields, "employment")


class ProjectPostWriteSerializer(_PostWriteBase):
    post_type = PostType.PROJECT
    detail_key, other_key = "project", "employment"
    detail_serializer = ProjectDetailSerializer
    project = ProjectDetailSerializer()

    class Meta(_PostWriteBase.Meta):
        fields = (*_PostWriteBase.Meta.fields, "project")


WRITE_SERIALIZERS = {
    PostType.EMPLOYMENT: EmploymentPostWriteSerializer,
    PostType.PROJECT: ProjectPostWriteSerializer,
}


# ------------------------------------------------------------------ read side
class _NamedRef(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PublicJobPostSerializer(serializers.ModelSerializer):
    """What anyone may see. No moderation data, no contact details."""

    employer = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    category = JobCategorySerializer(read_only=True)
    province = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    # Only the section matching the post type is present (the other key is omitted).
    employment = EmploymentDetailSerializer(source="employment_detail", read_only=True)
    project = ProjectDetailSerializer(source="project_detail", read_only=True)
    skills = JobPostSkillSerializer(source="post_skills", many=True, read_only=True)

    class Meta:
        model = JobPost
        fields = (
            "id",
            "post_type",
            "title",
            "description",
            "employer",
            "company",
            "category",
            "province",
            "city",
            "work_mode",
            "employment",
            "project",
            "skills",
            "published_at",
            "expires_at",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Exactly one detail section exists: drop the key of the other type.
        data.pop("project" if instance.post_type == PostType.EMPLOYMENT else "employment", None)
        return data

    def get_employer(self, obj) -> dict:
        return {"id": obj.employer_id, "display_name": obj.employer.display_name}

    def get_company(self, obj) -> dict | None:
        c = obj.company
        return {"id": c.pk, "name": c.name, "is_verified": c.is_verified} if c else None

    def get_province(self, obj) -> dict | None:
        return {"id": obj.province_id, "name": obj.province.name} if obj.province_id else None

    def get_city(self, obj) -> dict | None:
        return {"id": obj.city_id, "name": obj.city.name} if obj.city_id else None


class PublicJobPostListSerializer(PublicJobPostSerializer):
    """List rows carry a short excerpt instead of the full description."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        text = data.pop("description")
        data["description_excerpt"] = text if len(text) <= 300 else text[:300].rstrip() + "…"
        return data


class OwnerJobPostSerializer(PublicJobPostSerializer):
    """For the owner: adds state and the reviewer's note."""

    is_publicly_visible = serializers.SerializerMethodField()

    class Meta(PublicJobPostSerializer.Meta):
        fields = (
            *PublicJobPostSerializer.Meta.fields,
            "moderation_status",
            "lifecycle_status",
            "moderation_note",
            "duration_days",
            "is_publicly_visible",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_is_publicly_visible(self, obj) -> bool:
        return selectors.is_visible(obj)

from django.core.validators import RegexValidator
from django.utils import timezone
from rest_framework import serializers

from apps.locations.models import City, Province
from apps.skills.models import JobTitle, Skill

from . import services
from .models import (
    Certificate,
    DesiredJobTitle,
    Education,
    Language,
    PortfolioItem,
    Resume,
    ResumeSkill,
    WorkExperience,
)

MIN_DATE = timezone.datetime(1900, 1, 1).date()


def _today():
    return timezone.localdate()


# ---------------------------------------------------------------- children
class _ChildSerializer(serializers.ModelSerializer):
    """Base for resume sections. The resume comes from the view, never from the client."""

    @property
    def resume(self):
        return self.context["view"].get_resume()

    def _value(self, attrs, name):
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name, None) if self.instance else None

    def _check_order(self, attrs, start, end):
        first, last = self._value(attrs, start), self._value(attrs, end)
        if first and last and last < first:
            raise serializers.ValidationError({end: ["End date cannot be before start date."]})

    @staticmethod
    def _not_future(value):
        if value and value > _today():
            raise serializers.ValidationError("Date cannot be in the future.")
        return value


class EducationSerializer(_ChildSerializer):
    class Meta:
        model = Education
        fields = ("id", "degree", "field_of_study", "institution", "start_date", "end_date")

    def validate_start_date(self, value):
        return self._not_future(value)

    def validate(self, attrs):
        self._check_order(attrs, "start_date", "end_date")
        return attrs


class WorkExperienceSerializer(_ChildSerializer):
    class Meta:
        model = WorkExperience
        fields = (
            "id",
            "job_title",
            "company_name",
            "start_date",
            "end_date",
            "description",
            "responsibilities",
        )
        extra_kwargs = {
            "description": {"max_length": 2000},
            "responsibilities": {"max_length": 2000},
        }

    def validate_start_date(self, value):
        return self._not_future(value)

    def validate_end_date(self, value):
        return self._not_future(value)

    def validate(self, attrs):
        self._check_order(attrs, "start_date", "end_date")
        if self.instance is None and self.resume.has_no_work_experience:
            raise serializers.ValidationError(
                {"detail": "Your resume says you have no work experience. Turn that off first."}
            )
        return attrs


class ResumeSkillSerializer(_ChildSerializer):
    skill = serializers.PrimaryKeyRelatedField(queryset=Skill.objects.filter(is_active=True))
    skill_name_fa = serializers.CharField(source="skill.name_fa", read_only=True)
    skill_name_en = serializers.CharField(source="skill.name_en", read_only=True)

    class Meta:
        model = ResumeSkill
        fields = ("id", "skill", "skill_name_fa", "skill_name_en", "level")

    def validate_skill(self, skill):
        taken = ResumeSkill.objects.filter(resume=self.resume, skill=skill)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("This skill is already on your resume.")
        return skill


class DesiredJobTitleSerializer(_ChildSerializer):
    job_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects.filter(is_active=True))
    job_title_name_fa = serializers.CharField(source="job_title.name_fa", read_only=True)
    job_title_name_en = serializers.CharField(source="job_title.name_en", read_only=True)

    class Meta:
        model = DesiredJobTitle
        fields = ("id", "job_title", "job_title_name_fa", "job_title_name_en")

    def validate_job_title(self, job_title):
        if DesiredJobTitle.objects.filter(resume=self.resume, job_title=job_title).exists():
            raise serializers.ValidationError("This job title is already on your resume.")
        return job_title


class LanguageSerializer(_ChildSerializer):
    class Meta:
        model = Language
        fields = ("id", "name", "proficiency")

    def validate_name(self, value):
        from apps.common.text import normalize_text

        taken = Language.objects.filter(resume=self.resume, normalized_name=normalize_text(value))
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("This language is already on your resume.")
        return value


class CertificateSerializer(_ChildSerializer):
    class Meta:
        model = Certificate
        fields = ("id", "title", "issuer", "issue_date", "expiry_date", "credential_url")

    def validate_issue_date(self, value):
        return self._not_future(value)

    def validate(self, attrs):
        self._check_order(attrs, "issue_date", "expiry_date")
        return attrs


class PortfolioItemSerializer(_ChildSerializer):
    class Meta:
        model = PortfolioItem
        fields = ("id", "title", "url", "description")
        extra_kwargs = {"description": {"max_length": 1000}}


# ---------------------------------------------------------------- resume
class ResumeSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="job_seeker.first_name", read_only=True)
    last_name = serializers.CharField(source="job_seeker.last_name", read_only=True)
    province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(), required=False, allow_null=True
    )
    city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.select_related("province"), required=False, allow_null=True
    )
    contact_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        validators=[RegexValidator(r"^[0-9+\-\s]{5,20}$", "Enter a valid phone number.")],
    )
    has_photo = serializers.SerializerMethodField()
    completeness = serializers.SerializerMethodField()
    desired_job_titles = DesiredJobTitleSerializer(many=True, read_only=True)
    skills = ResumeSkillSerializer(many=True, read_only=True, source="resume_skills")
    educations = EducationSerializer(many=True, read_only=True)
    work_experiences = WorkExperienceSerializer(many=True, read_only=True)
    languages = LanguageSerializer(many=True, read_only=True)
    certificates = CertificateSerializer(many=True, read_only=True)
    portfolio_items = PortfolioItemSerializer(many=True, read_only=True)

    class Meta:
        model = Resume
        fields = (
            "id",
            "first_name",
            "last_name",
            "province",
            "city",
            "contact_email",
            "contact_phone",
            "date_of_birth",
            "has_photo",
            "introduction",
            "experience_level",
            "employment_status",
            "desired_work_modes",
            "expected_monthly_salary",
            "has_no_work_experience",
            "desired_job_titles",
            "skills",
            "educations",
            "work_experiences",
            "languages",
            "certificates",
            "portfolio_items",
            "completeness",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "introduction": {"max_length": 2000},
            "expected_monthly_salary": {"min_value": 1},
        }

    def get_has_photo(self, obj) -> bool:
        return bool(obj.photo)

    def get_completeness(self, obj) -> dict:
        return services.completeness(obj)

    def validate_date_of_birth(self, value):
        if value and (value > _today() or value < MIN_DATE):
            raise serializers.ValidationError("Enter a realistic date of birth.")
        return value

    def validate_desired_work_modes(self, value):
        return list(dict.fromkeys(value))

    def validate(self, attrs):
        instance = self.instance
        if attrs.get("city") is not None and "province" not in attrs:
            attrs["province"] = attrs["city"].province  # changing city implies its province
        city = attrs["city"] if "city" in attrs else (instance.city if instance else None)
        province = (
            attrs["province"] if "province" in attrs else (instance.province if instance else None)
        )
        if city is not None:
            if province is not None and province.pk != city.province_id:
                raise serializers.ValidationError(
                    {"city": ["City does not belong to the selected province."]}
                )
            attrs["province"] = city.province
        if attrs.get("has_no_work_experience") and instance and instance.work_experiences.exists():
            raise serializers.ValidationError(
                {"has_no_work_experience": ["Delete your work experience entries first."]}
            )
        return attrs


class PhotoUploadSerializer(serializers.Serializer):
    photo = serializers.FileField()

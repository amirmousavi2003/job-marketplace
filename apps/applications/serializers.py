from rest_framework import serializers

from . import services
from .models import (
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
    ProjectProposal,
    ProjectProposalStatusHistory,
    ProposalStatus,
)


# ------------------------------------------------------------------ input
class ApplicationCreateSerializer(serializers.Serializer):
    cover_letter = serializers.CharField(required=False, allow_blank=True, max_length=3000)


class ProposalCreateSerializer(serializers.Serializer):
    proposed_price = serializers.IntegerField(min_value=1, max_value=10**13)
    estimated_days = serializers.IntegerField(min_value=1, max_value=3650)
    description = serializers.CharField(min_length=20, max_length=3000)


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[])
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    status_choices: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = self.status_choices


class ApplicationTransitionSerializer(TransitionSerializer):
    status_choices = ApplicationStatus.choices


class ProposalTransitionSerializer(TransitionSerializer):
    status_choices = ProposalStatus.choices


# ------------------------------------------------------------------ output
class _PartyBase(serializers.ModelSerializer):
    """Context: `role` ("applicant" or "employer") = who is looking."""

    submitted_at = serializers.DateTimeField(source="created_at", read_only=True)
    job_post = serializers.SerializerMethodField()
    applicant = serializers.SerializerMethodField()
    allowed_next_statuses = serializers.SerializerMethodField()
    machine: services.Machine

    def get_job_post(self, obj) -> dict:
        post = obj.job_post
        return {
            "id": post.pk,
            "title": post.title,
            "post_type": post.post_type,
            "company": post.company.name if post.company else None,
        }

    def get_applicant(self, obj) -> dict:
        profile = obj.job_seeker
        return {"first_name": profile.first_name, "last_name": profile.last_name}

    def get_allowed_next_statuses(self, obj) -> list[str]:
        role = self.context.get("role")
        return self.machine.allowed_next(role, obj.status) if role else []


class ApplicationSerializer(_PartyBase):
    machine = services.APPLICATION

    class Meta:
        model = Application
        fields = (
            "id",
            "status",
            "cover_letter",
            "submitted_at",
            "updated_at",
            "job_post",
            "applicant",
            "allowed_next_statuses",
        )
        read_only_fields = fields


class ApplicationDetailSerializer(ApplicationSerializer):
    """Adds the frozen resume (what the employer reviews). Same data for both parties."""

    resume = serializers.JSONField(source="resume_snapshot", read_only=True)

    class Meta(ApplicationSerializer.Meta):
        fields = (*ApplicationSerializer.Meta.fields, "resume")
        read_only_fields = fields


class ProposalSerializer(_PartyBase):
    machine = services.PROPOSAL
    currency = serializers.CharField(source="job_post.project_detail.currency", read_only=True)
    contact = serializers.SerializerMethodField()

    class Meta:
        model = ProjectProposal
        fields = (
            "id",
            "status",
            "proposed_price",
            "estimated_days",
            "description",
            "currency",
            "submitted_at",
            "updated_at",
            "job_post",
            "applicant",
            "contact",
            "allowed_next_statuses",
        )
        read_only_fields = fields

    def get_contact(self, obj) -> dict | None:
        """Proposals carry no resume, so contact details are released only once the employer
        accepts the proposal, and only to the employer."""
        if self.context.get("role") != services.EMPLOYER or obj.status != ProposalStatus.ACCEPTED:
            return None
        profile = obj.job_seeker
        resume = getattr(profile, "resume", None)
        user = profile.user
        return {
            "email": (resume.contact_email if resume else "") or user.email,
            "phone": (resume.contact_phone if resume else "") or user.phone or "",
        }


class _HistoryBase(serializers.ModelSerializer):
    """Context: `applicant_user_id`. Shows the role of the actor, never an email."""

    by = serializers.SerializerMethodField()

    class Meta:
        fields = ("id", "from_status", "to_status", "by", "note", "created_at")
        read_only_fields = fields

    def get_by(self, obj) -> str:
        if obj.actor_id is None:
            return "system"
        return "applicant" if obj.actor_id == self.context["applicant_user_id"] else "employer"


class ApplicationHistorySerializer(_HistoryBase):
    class Meta(_HistoryBase.Meta):
        model = ApplicationStatusHistory


class ProposalHistorySerializer(_HistoryBase):
    class Meta(_HistoryBase.Meta):
        model = ProjectProposalStatusHistory

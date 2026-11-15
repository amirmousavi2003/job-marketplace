from rest_framework import serializers

from .models import Company, CompanyMembership


class CompanySerializer(serializers.ModelSerializer):
    my_role = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = (
            "id",
            "name",
            "description",
            "website",
            "is_verified",
            "my_role",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_verified", "my_role", "created_at", "updated_at")


class MembershipSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="employer.display_name", read_only=True)
    email = serializers.EmailField(source="employer.user.email", read_only=True)

    class Meta:
        model = CompanyMembership
        fields = ("id", "display_name", "email", "role", "created_at")
        read_only_fields = fields


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()

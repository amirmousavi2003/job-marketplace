from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import services
from .models import iran_mobile_validator
from .services import get_user_for_reset

User = get_user_model()


def _phone_field():
    return serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=11,
        validators=[iran_mobile_validator],
    )


def _check_phone_unique(value, exclude_pk=None):
    if value and User.objects.filter(phone=value).exclude(pk=exclude_pk).exists():
        raise serializers.ValidationError("This phone number is already registered.")
    return value or None


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    phone = _phone_field()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "email", "phone", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_phone(self, value):
        return _check_phone_unique(value)

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], user=User(email=attrs["email"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        return services.register_user(
            email=validated_data["email"],
            password=validated_data["password"],
            phone=validated_data.get("phone"),
        )


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        return super().validate(attrs)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value, user=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = get_user_for_reset(attrs["uid"], attrs["token"])
        if user is None:
            raise serializers.ValidationError(
                {"token": ["Invalid or expired reset link."]}, code="invalid_token"
            )
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        attrs["user"] = user
        return attrs


class DeactivateSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Password is incorrect.")
        return value


class MeSerializer(serializers.ModelSerializer):
    phone = _phone_field()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "phone", "date_joined", "roles")
        read_only_fields = ("id", "email", "date_joined", "roles")

    def validate_phone(self, value):
        return _check_phone_unique(value, exclude_pk=self.instance.pk)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "is_job_seeker": {"type": "boolean"},
                "is_employer": {"type": "boolean"},
                "is_admin": {"type": "boolean"},
            },
        }
    )
    def get_roles(self, obj):
        return {
            "is_job_seeker": hasattr(obj, "job_seeker_profile"),
            "is_employer": hasattr(obj, "employer_profile"),
            "is_admin": obj.is_staff,
        }

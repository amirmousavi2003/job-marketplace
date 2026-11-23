from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView, GenericAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import serializers, services
from .tasks import send_password_reset_email

User = get_user_model()


class RegisterView(CreateAPIView):
    """Create an account (email + password, optional Iranian mobile number). Returns the new
    account without any token: log in next."""

    serializer_class = serializers.RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth_register"


class LoginView(TokenObtainPairView):
    serializer_class = serializers.LoginSerializer
    throttle_scope = "auth_login"


class LogoutView(GenericAPIView):
    """Blacklists the given refresh token. The refresh token itself is the credential."""

    serializer_class = serializers.LogoutSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise ValidationError({"refresh": ["Invalid or expired token."]}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(GenericAPIView):
    """Change the password. All refresh tokens of the account are revoked, so every device must
    log in again."""

    serializer_class = serializers.PasswordChangeSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(request.user, serializer.validated_data["new_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(GenericAPIView):
    """Always answers 200 so the endpoint cannot be used to discover registered emails."""

    serializer_class = serializers.PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth_password_reset"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            send_password_reset_email.delay(user.pk)
        return Response({"detail": "If the email is registered, a reset link has been sent."})


class PasswordResetConfirmView(GenericAPIView):
    """Set a new password with the uid and token from the reset email (valid for one hour,
    single use). Revokes all refresh tokens."""

    serializer_class = serializers.PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth_password_reset"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(
            serializer.validated_data["user"], serializer.validated_data["new_password"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(RetrieveUpdateAPIView):
    """The logged-in account: email, phone, join date and roles (job seeker / employer /
    admin). Only the phone number can be edited."""

    serializer_class = serializers.MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class DeactivateAccountView(GenericAPIView):
    """Deactivate the account (password required). Login becomes impossible and all tokens are
    revoked. For permanent deletion use the erase endpoint."""

    serializer_class = serializers.DeactivateSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.deactivate_account(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services


class EraseAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    confirm = serializers.BooleanField(help_text="Must be true: erasure cannot be undone.")

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Password is incorrect.")
        return value

    def validate_confirm(self, value):
        if value is not True:
            raise serializers.ValidationError("Send confirm=true to confirm the erasure.")
        return value


class EraseAccountView(GenericAPIView):
    """Permanently anonymize the account and delete its personal data. Cannot be undone."""

    serializer_class = EraseAccountSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = "account_erase"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.erase_account(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

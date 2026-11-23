from django.db import connection
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness/readiness probe. Public. Checks DB connectivity."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []

    @extend_schema(
        responses={
            200: inline_serializer("HealthOk", {"status": serializers.CharField()}),
            503: OpenApiResponse(description="Database unavailable"),
        }
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response({"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


def _api_error(request, status_code: int, code: str, message: str):
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": {}}}, status=status_code
    )


def json_not_found(request, exception=None):
    """Unknown URLs under /api/ answer with the same JSON error shape as everything else."""
    if request.path.startswith("/api/"):
        return _api_error(request, 404, "not_found", "Not found.")
    from django.views.defaults import page_not_found

    return page_not_found(request, exception)


def json_server_error(request):
    """Unexpected errors never leak details to clients (details go to the server log)."""
    if request.path.startswith("/api/"):
        return _api_error(request, 500, "server_error", "Internal server error.")
    from django.views.defaults import server_error

    return server_error(request)

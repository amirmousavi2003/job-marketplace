"""Single, predictable error envelope for every API error.

{"error": {"code": "...", "message": "...", "details": {...}}}
"""

from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

_CODES = {
    drf_exceptions.ValidationError: "validation_error",
    drf_exceptions.AuthenticationFailed: "authentication_failed",
    drf_exceptions.NotAuthenticated: "not_authenticated",
    drf_exceptions.PermissionDenied: "permission_denied",
    drf_exceptions.NotFound: "not_found",
    drf_exceptions.MethodNotAllowed: "method_not_allowed",
    drf_exceptions.Throttled: "throttled",
    drf_exceptions.ParseError: "parse_error",
}


def _code_for(exc) -> str:
    for cls, code in _CODES.items():
        if isinstance(exc, cls):
            return code
    return getattr(exc, "default_code", "error")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django returns 500 without leaking details

    data = response.data
    if isinstance(exc, drf_exceptions.ValidationError):
        details = data
        message = "Validation failed."
    else:
        details = {}
        message = str(data.get("detail", exc)) if isinstance(data, dict) else str(data)

    return Response(
        {"error": {"code": _code_for(exc), "message": message, "details": details}},
        status=response.status_code,
        headers=dict(response.items()),
    )

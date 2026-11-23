from django.conf import settings
from django.http import JsonResponse


class RequestSizeLimitMiddleware:
    """Refuse oversized API requests early (HTTP 413) based on Content-Length.

    Django's DATA_UPLOAD_MAX_MEMORY_SIZE does not apply to JSON bodies read by DRF, so without
    this a client could make the server parse arbitrarily large JSON. A reverse proxy should
    enforce the same limit (see docs/deployment.md)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            is_upload = request.content_type == "multipart/form-data"
            limit = settings.MAX_UPLOAD_BODY_BYTES if is_upload else settings.MAX_JSON_BODY_BYTES
            if length > limit:
                return JsonResponse(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "Request body is too large.",
                            "details": {},
                        }
                    },
                    status=413,
                )
        return self.get_response(request)

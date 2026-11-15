import pytest
from rest_framework import exceptions

from apps.common.exceptions import api_exception_handler


@pytest.mark.django_db
def test_health_endpoint_is_public(api_client):
    response = api_client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_swagger_schema_generates(api_client):
    response = api_client.get("/api/schema/")
    assert response.status_code == 200


def test_error_envelope_for_validation_error():
    response = api_exception_handler(
        exceptions.ValidationError({"email": ["Invalid."]}), {"view": None, "request": None}
    )
    assert response.status_code == 400
    body = response.data["error"]
    assert body["code"] == "validation_error"
    assert body["details"] == {"email": ["Invalid."]}


def test_error_envelope_for_permission_denied():
    response = api_exception_handler(exceptions.PermissionDenied(), {"view": None, "request": None})
    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"

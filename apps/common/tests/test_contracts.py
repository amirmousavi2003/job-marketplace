"""Guards the contracts other people depend on: the frontend developer's OpenAPI file and the
generated database documentation. If they are stale these tests tell you the exact command."""

import io
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator

ROOT = Path(__file__).resolve().parents[3]


def test_committed_openapi_file_matches_the_code():
    generated = yaml.safe_load(
        yaml.dump(dict(SchemaGenerator().get_schema(request=None, public=True)))
    )
    committed = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())
    assert generated == committed, (
        "docs/api/openapi.yaml is out of date. Regenerate it with:\n"
        "  python manage.py spectacular --validate --fail-on-warn --file docs/api/openapi.yaml"
    )


def test_every_operation_is_documented_and_secured_consistently():
    spec = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())
    operations = [
        (path, method, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operations) > 100
    assert all(op.get("description") or op.get("summary") for _, _, op in operations)
    assert len({op["operationId"] for _, _, op in operations}) == len(operations)
    assert spec["components"]["securitySchemes"]["jwtAuth"]["scheme"] == "bearer"


def test_committed_erd_matches_the_models():
    out = io.StringIO()
    call_command("generate_erd", stdout=out)
    assert out.getvalue().strip() == (ROOT / "docs/erd.md").read_text().strip(), (
        "docs/erd.md is out of date. Regenerate it with:\n"
        "  python manage.py generate_erd > docs/erd.md"
    )


def test_erd_contains_the_key_relations_and_rules():
    out = io.StringIO()
    call_command("generate_erd", stdout=out)
    text = out.getvalue()
    assert "erDiagram" in text and 'JobPost ||--o| EmploymentDetail : "job_post"' in text
    assert "| `Application.job_post` | JobPost | PROTECT | no |" in text
    assert "jobs_employment_salary_range" in text and "applications_one_per_seeker_post" in text
    assert "composite foreign keys" in text


@pytest.mark.parametrize(
    "name", ["README.md", ".env.example", ".gitignore", "Dockerfile", "docker-compose.yml"]
)
def test_project_files_exist(name):
    assert (ROOT / name).exists()


def test_no_secrets_are_committed():
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore and "!.env.example" in gitignore
    example = (ROOT / ".env.example").read_text()
    for line in example.splitlines():
        if line.startswith(("AI_EMBEDDING_API_KEY=", "DJANGO_SECRET_KEY=", "POSTGRES_PASSWORD=")):
            value = line.split("=", 1)[1]
            assert value in {"", "change-me", "change-me-to-a-long-random-string"}, line

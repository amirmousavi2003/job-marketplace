# Job Marketplace Backend

Django + DRF + PostgreSQL backend for an Iranian employment and freelance project marketplace.
Architecture and decisions: `docs/phase1-architecture-blueprint.md`.

## Status

| Phase | Status |
|---|---|
| 1. Blueprint | done |
| 2. Foundation (settings, custom User, Docker, tests) | done |
| 3. Auth, profiles, companies | done (see `docs/phase3-api-auth-profiles-companies.md`) |
| 4. Resume, skills taxonomy, locations | done (see `docs/phase4-api-resume-taxonomy.md`) |
| 5. Job marketplace (posts, search, moderation) | done (see `docs/phase5-api-jobs-moderation.md`) |
| 6. Applications and project proposals | done (see `docs/phase6-api-applications-proposals.md`) |
| 7. AI matching | next |

## Run with Docker

```bash
cp .env.example .env        # then edit POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up --build
```

- API health: http://localhost:8000/api/v1/health/
- Swagger UI: http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/ (create a superuser first)

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web pytest
```

## Run without Docker

Needs Python 3.12+ and a PostgreSQL server.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env        # set POSTGRES_HOST=localhost
python manage.py migrate
python manage.py runserver
```

## Demo catalogue

```bash
docker compose exec web python manage.py seed_demo_catalogue
```

Needs PostgreSQL with the `pg_trgm` extension (included in the official image; the DB user
must be allowed to create extensions, which the Docker setup allows).

## Expired posts

Schedule `python manage.py expire_jobs` daily (cron or Celery beat). Expired posts are hidden from
search immediately even without it; the command only updates their stored status.

## Tests and lint

```bash
pytest
ruff check . && ruff format --check .
```

Tests use `config.settings.test` and need PostgreSQL (the DB user must be able to create a test database).

## Settings

- `config/settings/base.py`: shared. Secrets only from environment variables.
- `dev.py`, `test.py`, `prod.py`: per environment. `prod.py` enables HTTPS-only cookies, HSTS and SSL redirect.
- `manage.py` defaults to `dev`; `wsgi.py` / `asgi.py` default to `prod`.

## Conventions

- Error format for every API error: `{"error": {"code", "message", "details"}}`.
- Pagination: `?page=&page_size=` (max 50) returns `{count, next, previous, results}`.
- Dev runs Celery tasks inline (`CELERY_TASK_ALWAYS_EAGER=True` in `dev.py`), so password-reset emails
  are printed in the web container log. Production needs a real worker and SMTP.
- Emails are stored lowercase; login identifier is the email.
- Money is stored as integers (Rial). Dates are ISO 8601 Gregorian; the frontend converts to Jalali.

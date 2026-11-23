# Job Marketplace Backend

Backend of an employment and freelance-project marketplace for Iran. Django 5.2 + Django REST Framework +
PostgreSQL + Redis + Celery. Persian is first-class (search, validation, messages). The React frontend is a
separate project; this repository only provides the API.

- Job seekers build a resume, apply to jobs and send proposals for projects.
- Employers (individuals or companies) post jobs and projects; **an admin approves every post** before it is public.
- Search and filters, explainable AI-assisted recommendations, full status history, privacy by design.

Status: **all 8 phases done.** See `docs/COMPLETION_REPORT.md` for what was verified and what was not.

## Run it (Docker)

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
# edit .env: set POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo_catalogue     # optional demo skills and job titles
docker compose exec web pytest                                   # all tests
```

| What | Where |
|---|---|
| API health | http://localhost:8000/api/v1/health/ |
| Interactive API docs (development only) | http://localhost:8000/api/docs/ |
| Django admin | http://localhost:8000/admin/ |
| API contract for the frontend developer | `docs/api/openapi.yaml` |

Optional background services (real Celery worker + nightly expiry job):
`docker compose --profile async up -d`, and set `CELERY_TASK_ALWAYS_EAGER=False` in `.env`.
Stop with `docker compose down` (data is kept in volumes; `down -v` would erase it).

## Run it without Docker

Needs Python 3.12+, PostgreSQL 16 and (for production-like runs) Redis.

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
cp .env.example .env     # set POSTGRES_HOST=localhost and the database credentials
python manage.py migrate
python manage.py runserver
```

## Tests and quality

```bash
pytest                                  # 759 tests (real PostgreSQL required)
ruff check . && ruff format --check .   # lint and format
python manage.py check --deploy         # with config.settings.prod
```

Tests use `config.settings.test` automatically. Two "contract" tests fail if `docs/api/openapi.yaml` or
`docs/erd.md` is out of date; they print the exact command to regenerate them.

## Project layout

```
config/            settings (base, dev, test, prod), urls, celery
apps/              accounts, privacy, profiles, companies, locations, skills, resumes,
                   jobs, moderation, applications, matching, common
docs/              guides (see below), api/openapi.yaml, erd.md
requirements/      base.txt, dev.txt
```

## Configuration

All settings come from environment variables; `.env.example` lists them with comments. The important ones:
`DJANGO_SECRET_KEY`, `POSTGRES_*`, `REDIS_URL`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL`, `AI_EMBEDDING_PROVIDER`.
Production-only settings and the checklist are in `docs/deployment.md`.

## AI matching

Works out of the box with a free offline engine (`AI_EMBEDDING_PROVIDER=local_ngram`) that measures **text
overlap, not meaning**. It is assistive only and labeled honestly in every response. A real embeddings service
can be connected later with three environment variables. See `docs/phase7-ai-matching.md`.

## Useful commands

| Command | Purpose |
|---|---|
| `seed_demo_catalogue` | demo skills and job titles (idempotent) |
| `expire_jobs` | mark expired posts (beat runs it nightly) |
| `compute_embeddings` | prepare text vectors for public posts |
| `generate_erd > docs/erd.md` | regenerate the database documentation |
| `spectacular --validate --fail-on-warn --file docs/api/openapi.yaml` | regenerate the API contract |

## Documentation

| File | For |
|---|---|
| `docs/frontend-integration.md` | the React developer: auth, errors, pagination, flows, enum values |
| `docs/api/openapi.yaml` | machine-readable API (116 operations) |
| `docs/phase3-...` to `docs/phase7-...` | endpoint-by-endpoint rules and examples per feature area |
| `docs/architecture.md` | how the system is built and why |
| `docs/erd.md` | generated database design, deletion rules, constraints |
| `docs/security.md` | controls, how they were verified, known limitations |
| `docs/deployment.md` | production checklist, nginx example, operations |
| `docs/COMPLETION_REPORT.md` | final report: results, findings, risks, next steps |
| `docs/phase1-architecture-blueprint.md` | the original plan (historical; the architecture file wins) |

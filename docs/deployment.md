# Deployment guide

> **Honesty note.** The code was verified on this project's test machine with PostgreSQL 16, Redis, gunicorn and
> the production settings. The Docker files were **not executed there** (no Docker available); the compose
> file is for development. The production recipe below is a checklist, not a tested script: try it on a
> staging server first.

## What you need

PostgreSQL 16 (with the `pg_trgm` extension, included in the official image; the DB user must be allowed to
create it), **Redis** (required in production), Python 3.12, a reverse proxy with HTTPS (nginx/Caddy), an
SMTP account for password-reset emails.

## Settings (environment variables, never in Git)

| Variable | Production value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | 50+ random chars: `python -c "import secrets;print(secrets.token_urlsafe(64))"`. Changing it logs everyone out |
| `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | your API domain(s); `CORS_ALLOWED_ORIGINS` = the frontend origin(s) |
| `POSTGRES_*` | database name, user, a strong password, host |
| `REDIS_URL` | **required**: startup fails without it (shared rate-limit counters) |
| `DJANGO_NUM_PROXIES` | `1` behind one proxy. Wrong value = everyone shares one rate limit, or limits can be spoofed |
| `DJANGO_ADMIN_URL` | something unguessable, e.g. `manage-k3j9x/` |
| `DJANGO_ENABLE_API_DOCS` | leave `False`; give the frontend developer `docs/api/openapi.yaml` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | your SMTP account |
| `FRONTEND_URL`, `DEFAULT_FROM_EMAIL` | used in password-reset emails |
| `CELERY_TASK_ALWAYS_EAGER` | `False` (and run the worker) |
| `AI_EMBEDDING_PROVIDER` | `local_ngram` (default, nothing leaves your server) or `openai_compatible` + URL/KEY/MODEL |

## Steps

```bash
git pull && pip install -r requirements/base.txt
python manage.py migrate
python manage.py collectstatic --noinput        # only needed for the Django admin pages
python manage.py createsuperuser                # first admin
python manage.py check --deploy                 # expect only the HSTS-preload note (deliberate)
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
celery -A config worker -l info                 # background jobs (embeddings, reset emails)
celery -A config beat -l info                   # nightly expiry of old posts
```

With Docker the same processes are the `web`, `worker` and `beat` services
(`docker compose --profile async up -d`). The shipped `docker-compose.yml` runs the development server;
for production override the `web` command with gunicorn, drop the source-code volume and do not publish the
database or Redis ports.

## Reverse proxy (nginx example)

```nginx
server {
  listen 443 ssl http2;
  server_name api.example.ir;
  client_max_body_size 3m;                       # same limit as the app (photo upload)
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;   # overwrite, never append client-supplied values
    proxy_set_header X-Forwarded-Proto $scheme;
  }
  location /media/ { deny all; }                 # photos are private: served only through the API
}
```

Rate limits and the Django admin deserve extra protection at the proxy (for example restrict the admin URL by IP).

## Operations

- **Backups:** PostgreSQL dumps (`pg_dump`) daily, tested restores. The `media/` folder holds resume photos.
- **Expiry:** beat runs `expire_jobs` nightly (03:00 Tehran). Posts past their date are hidden immediately anyway.
- **AI vectors:** `python manage.py compute_embeddings` prepares vectors for existing posts.
- **Logs:** gunicorn/Celery write to stdout. Do not log request bodies (they contain passwords).
- **Upgrades:** `migrate` is always safe to re-run. Never edit an applied migration.
- **Scaling:** more gunicorn workers first; recommendations are CPU-bound Python (about 0.2 to 0.4 s for 200
  posts). A move to `pgvector` is the next step if semantic search must cover tens of thousands of posts.

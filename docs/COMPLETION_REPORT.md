# Completion report

## Summary

A complete backend for an Iranian job and freelance-project marketplace, built in 8 phases.

| | |
|---|---|
| Apps | 12 domain apps (modular monolith) |
| API | 116 operations on 75 paths, versioned `/api/v1/`, OpenAPI 3 file validated |
| Tests | **759 passed**, 34 skipped by design (parametrized "open by design" rows of the security matrix) |
| Code | about 7,500 lines of application code and 6,100 lines of tests |
| Quality gates | `ruff` clean, migrations in sync with models, OpenAPI file and ERD match the code (contract tests) |

## Requirements coverage

| Spec section | Status |
|---|---|
| 1 Stack (Python 3.12, Django, DRF, PostgreSQL, Docker, Redis, Celery, JWT, OpenAPI, pytest, Ruff) | Done. Django 5.2 **LTS** was chosen over the newest release for stability |
| 2-4 Product, accounts, employers and companies | Done. One account can be seeker and employer; company optional |
| 5-6 Resume builder, skills and job-title catalogue with aliases and moderated suggestions | Done, including photo handling |
| 7-8 Job posts (employment / project, separate details) and admin moderation | Done. The database itself enforces type consistency. State split into moderation + lifecycle |
| 9-11 Applications, proposals, status history | Done. Resume snapshot per application; separate history tables |
| 12 AI matching | Done with an honest fallback. The default engine is **lexical** (text overlap), not a neural model. A neural service can be plugged in; **that path was tested against a simulated service only** |
| 13-14 API design, search and filtering | Done |
| 15 Security and privacy | Done, plus account erasure (see Findings) |
| 16 Database design | Done. Generated documentation: `docs/erd.md` |
| 17 Testing | Done |
| 18 Docker | Files delivered. Run by the project owner up to phase 6 (260 / 358 tests passed there) |
| 19-21 Code quality, workflow, frontend readiness | Done. `docs/frontend-integration.md` and `docs/api/openapi.yaml` |

Deliberately left out (as the spec said): frontend, payments, chat. Left out by decision: notifications
(email/SMS) for status changes.

## Phase 8 review: findings and fixes

| # | Finding | Impact | Resolution |
|---|---|---|---|
| 1 | Rate limiting only on a few sensitive endpoints | public search could be hammered | global limits for anonymous and logged-in users, per-feature limits kept |
| 2 | **Rate limits were per process** when no shared cache is configured. Found by running 2 gunicorn workers: 11 wrong logins were all accepted | security limits silently several times weaker | production now **refuses to start without `REDIS_URL`**; verified again with Redis (10 accepted, then 429) |
| 3 | Django's body-size setting does not apply to DRF JSON bodies | oversized JSON could be parsed | middleware rejects over 1 MB (3 MB for photo) with 413 |
| 4 | Unknown `/api/` URLs and server errors answered with HTML | frontend would break on parse | JSON error shape for 404 and 500, no details leaked |
| 5 | Swagger and `/admin/` publicly reachable at default addresses in production | information exposure, guessable admin | docs off by default in production, admin URL configurable |
| 6 | No permanent account deletion (promised in the blueprint) | privacy | `POST /accounts/me/erase/`: anonymizes the account, deletes resume, photo, AI matches, applicant texts; keeps employers' history without personal data |
| 7 | **Production could not send password-reset emails** (no SMTP settings) | feature broken on a real server | SMTP settings from the environment, retries when the mail server is down |
| 8 | Recommendations scored only the newest 200 posts | old but well-fitting posts never shown | candidate pool picks relevant posts first (shared skills / desired titles), newest ones only top it up |
| 9 | Cosine similarity cost in pure Python | recommendation latency | vectors stored normalized; about 30% faster |
| 10 | Nothing prevented a future endpoint from being public by mistake | process risk | whole-API **authorization matrix** test (231 checks) |
| 11 | API file / ERD could drift from the code | frontend confusion | contract tests fail with the exact regeneration command |

Bugs caught earlier by tests in phases 2-7 (examples): `ftp://` links passing a validator DRF silently drops, a
missing migration hidden by a pipe, a hard-constraint warning dropped from the top reasons, a `KeyError` in the
scoring of non-applicable factors. Each was fixed and kept as a regression test.

## Performance (indicative, development machine)

Synthetic data: 6,000 public posts, 800 resumes, 200 applicants on one post.

| Operation | Time | Queries |
|---|---|---|
| public list, filters, detail, my posts, my applications | 25 to 90 ms | 3 to 8, constant as data grows |
| keyword search (Persian, several words) | about 50 to 85 ms; the trigram index serves selective words in about 0.1 ms | 3 |
| recommendations (200 candidates), unchanged inputs / first computation | about 0.2 s / 0.4 s | about 15 |
| AI ordering of 200 applicants | about 0.2 s | about 10 |

Query counts are guarded by tests so N+1 problems cannot return unnoticed.

## What was verified, and what was not

Verified: the full test suite on a clean Python environment built only from `requirements/`; the application
under gunicorn with the production settings (headers, throttling with Redis and 2 workers, 413, JSON errors,
docs off, renamed admin); `check --deploy`; performance on synthetic data; the HTTP embedding client against a
local simulated OpenAI-style service (success, outage, wrong key); the Docker setup by the project owner through phase 6.

**Not verified:** Docker for phases 7 and 8 and the optional `async` profile; production compose and nginx
recipes (a checklist is provided); a real SMTP server; a real embeddings provider; load above a few thousand
posts; the React frontend; HTTPS and backup/restore procedures.

## Risks and decisions before launch

1. **Trust and safety:** no email verification and no two-factor login. Decide whether admins and employers need them.
2. **Moderation workload:** every post needs an admin. Plan who reviews, and how fast.
3. **AI and privacy:** a networked embeddings provider receives resume and post text. Informing users and
   checking the provider's terms is required first. The default local engine sends nothing out.
4. **Infrastructure:** Redis is mandatory in production; photos live on local disk (move to object storage
   when running several servers); add error monitoring and backups.
5. **Content:** the city list is not complete and the skill and job-title catalogue is only a demo set.
6. **Scale:** beyond tens of thousands of posts, move text vectors to `pgvector` and precompute recommendations.
7. **Account discovery** through sign-up and "add member by email" is throttled but possible (documented).

## Suggested next steps

Connect the React frontend using `docs/frontend-integration.md`; deploy to a staging server and follow
`docs/deployment.md`; add notifications and email verification; build the admin moderation screens; then evaluate
a real embeddings service on real Persian data before relying on it.

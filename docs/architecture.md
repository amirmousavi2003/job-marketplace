# Architecture (as built)

Modular monolith: Django 5.2 LTS, Django REST Framework, PostgreSQL 16, Redis, Celery. One deployable unit,
domain-oriented apps, REST API under `/api/v1/`. The first plan is `docs/phase1-architecture-blueprint.md`;
where it differs from this file, **this file is right**. The database design is generated from the code in
`docs/erd.md` (ERD, deletion rules, constraints).

## Apps

| App | Owns |
|---|---|
| `common` | base model, error format, pagination, Persian text normalization, health check, size-limit middleware, `generate_erd` |
| `accounts` | custom `User` (email login), JWT auth, password change/reset, deactivation |
| `privacy` | irreversible account erasure (anonymization) |
| `profiles` | `JobSeekerProfile`, `EmployerProfile` (one account may have both) |
| `companies` | `Company`, `CompanyMembership` (optional for employers, several members) |
| `locations` | provinces and cities (reference data) |
| `skills` | skills, job titles, categories, aliases, user suggestions with admin moderation |
| `resumes` | one resume per seeker and its sections, photo handling |
| `jobs` | `JobPost` + `EmploymentDetail` / `ProjectDetail`, search and filters, lifecycle |
| `moderation` | review workflow of posts and its append-only history |
| `applications` | `Application`, `ProjectProposal`, their status machines and histories |
| `matching` | embedding providers, scoring, stored matches, background tasks |

Inside an app: `models` (and DB constraints) -> `services` (business rules, transactions) -> `selectors`
(queries) -> `serializers`/`views` (thin). Dependencies point one way; no import cycles.

## Key decisions

- **One account, several roles.** Role = which profile exists. All authorization is server-side.
- **Two post types, separate detail tables.** The database enforces the match (composite foreign keys).
- **Moderation state and lifecycle state are separate fields.** Public means: approved + active + not expired +
  active employer and company, defined once (`jobs/selectors.py`).
- **Applications and proposals are different entities**, each with its own statuses and history table.
- **Resume snapshot** (JSON) is stored with each application so history cannot change silently.
- **Catalogue terms** (names and aliases) are unique after Persian normalization.
- **Business rules in the database too**: check constraints, partial unique indexes, protected deletions.
- **AI is assistive**: structured, explainable scoring first; text similarity is an optional part; failures degrade
  to structured-only and say so.

## Differences from the first blueprint

| Blueprint | As built | Why |
|---|---|---|
| single status list for posts | `moderation_status` + `lifecycle_status` | independent concerns |
| `WITHDRAWN` only for proposals | also for applications | applicants can step back; erasure uses it |
| provinces/cities free text | reference tables | reliable filtering |
| admin API under `/admin-api/` | `/api/v1/admin/...` | one versioned prefix |
| resume names on the resume | names come from the profile | one source of truth |
| `expected_monthly_salary` not listed | added to the resume | AI matching needs it |
| matching with a neural model | local lexical engine by default, neural optional | no free verified service; honest labeling |
| `is_stale` on AI matches | `inputs_hash` | recompute exactly when an input changes |
| no `privacy` app | added | erasure touches many apps |

## State machines

- Post moderation: `DRAFT -> PENDING_REVIEW -> APPROVED | REJECTED`; editing approved -> `PENDING_REVIEW`; editing rejected -> `DRAFT`.
- Post lifecycle: `ACTIVE <-> DEACTIVATED`, `ACTIVE -> EXPIRED` (renewable).
- Application: `PENDING -> REVIEWING -> INTERVIEW -> ACCEPTED`, rejection from any open state; applicant may `WITHDRAW`.
- Proposal: `PENDING -> REVIEWING -> NEGOTIATING -> ACCEPTED`, same rejection/withdraw rules.

Allowed moves and who may make them are in `apps/applications/services.py` and `apps/moderation/services.py`.

## Testing

pytest + pytest-django on a real PostgreSQL (partial indexes, trigram indexes and composite foreign keys need it).
Layers: DB constraint tests, service tests, API tests (permissions, IDOR, validation, mass assignment), contract
tests (OpenAPI file and ERD must match the code), a whole-API authorization matrix, and query-count guards against
N+1 problems. Run: `pytest`, lint: `ruff check . && ruff format --check .`.

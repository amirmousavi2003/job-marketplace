# API guide — Job posts, search, moderation (Phase 5)

Same conventions as before (error envelope, Bearer auth, pagination `{count,next,previous,results}`).
Live docs: `/api/docs/`.

## Design decisions

- **Two post types, two detail tables.** `JobPost` is shared. `EMPLOYMENT` posts have an
  `employment` section, `PROJECT` posts a `project` section. Responses contain only the section that
  matches the type. The database itself forbids a mismatch (composite foreign keys in
  `jobs/migrations/0001_initial.py` + CHECK constraints). A post and its detail are created in one transaction.
- **Two separate state fields** (this splits your single status list):
  `moderation_status` = `DRAFT | PENDING_REVIEW | APPROVED | REJECTED`,
  `lifecycle_status` = `ACTIVE | DEACTIVATED | EXPIRED`.
  A post is public only if `APPROVED` + `ACTIVE` + `expires_at` in the future + the employer account
  is active + its company (if any) is active. This rule exists once (`jobs/selectors.py: visible_q`).
- **Editing re-enters moderation.** Editing an `APPROVED` post sends it back to `PENDING_REVIEW` and hides it
  until re-approved. Editing a `REJECTED` post returns it to `DRAFT`. Editing a draft or pending post keeps its status.
- **Expiry.** `duration_days` (1 to 90, default 30) is chosen by the employer. At approval,
  `expires_at = approval time + duration_days`. Expired posts are hidden immediately (the date is checked on every
  query). The `expire_jobs` command (or the Celery task `apps.jobs.tasks.expire_overdue_posts`)
  additionally sets `lifecycle_status=EXPIRED`; schedule it daily (cron or Celery beat).
- **Money.** Salary is Rial per month. Project budget has a `currency` (`IRR` or `USD`); the API never converts currencies.
- **Keyword search** uses a normalized text column (Persian/Arabic letters, ZWNJ, digits, case) with a PostgreSQL
  trigram index. All words must match (AND). Titles that contain the whole phrase rank first.
  Search text includes title, description, employer name, company, category, province, city and skill names;
  it is rebuilt when a post is created or edited (renaming a category later does not rewrite old posts).
- **Anti-abuse.** Creating posts is throttled (30/hour); at most 10 posts can wait for review per employer;
  at most 20 skills per post.

## Public endpoints (no login)

| Method | URL | Notes |
|---|---|---|
| GET | `/jobs/` | search all published posts |
| GET | `/jobs/employment/` | same, employment only |
| GET | `/jobs/projects/` | same, projects only |
| GET | `/jobs/{id}/` | 404 unless published. The owner can still open their own post |

List rows contain `description_excerpt` (300 chars) instead of `description`.
Public data never includes moderation fields, contact details or the employer's email.

### Filters (all combine with AND, invalid values return 400)

| Param | Meaning |
|---|---|
| `q` | keyword(s) |
| `category` | category id; a top-level id includes its sub-categories |
| `type` | `EMPLOYMENT` or `PROJECT` |
| `province`, `city` | ids from `/locations/...` |
| `work_mode` | `ON_SITE`, `REMOTE`, `HYBRID` |
| `employment_type` | `FULL_TIME PART_TIME CONTRACT INTERNSHIP TEMPORARY` (employment posts only) |
| `experience_level` | `NO_EXPERIENCE JUNIOR MID SENIOR` (employment posts only) |
| `salary_min`, `salary_max` | range overlap: `salary_min=X` keeps posts that can pay at least X; `salary_max=Y` keeps posts that start at or below Y. Employment posts only |
| `budget_min`, `budget_max` | same idea for project budgets. Project posts only |
| `skills` | comma-separated skill ids (max 20). `skills_match=any` (default) or `all` |
| `published_after` | date `YYYY-MM-DD` |
| `ordering` | `published_at`, `-published_at` (default), `expires_at`, `-expires_at` |
| `page`, `page_size` | page size max 50 |

## Employer endpoints (employer profile required)

| Method | URL | Notes |
|---|---|---|
| POST | `/jobs/employment/` | create a DRAFT |
| POST | `/jobs/projects/` | create a DRAFT |
| GET | `/jobs/mine/` | my posts in every state. Filters: `type`, `moderation_status`, `lifecycle_status` |
| PATCH | `/jobs/{id}/` | partial update, nested `employment`/`project` can be partial, `skills` replaces the list |
| DELETE | `/jobs/{id}/` | only DRAFT or REJECTED (otherwise 409) |
| POST | `/jobs/{id}/submit/` | DRAFT or REJECTED to PENDING_REVIEW |
| POST | `/jobs/{id}/deactivate/` | approved + active to DEACTIVATED |
| POST | `/jobs/{id}/activate/` | DEACTIVATED to ACTIVE (409 if expired, renew instead) |
| POST | `/jobs/{id}/renew/` | approved post: new `expires_at`, no new review |

Other employers' posts return 404 on every endpoint.
Fields the client cannot set (and which are ignored if sent): `employer`, `post_type`, statuses,
`published_at`, `expires_at`, `moderation_note`.

Create example:

```json
POST /api/v1/jobs/employment/
{
  "title": "برنامه‌نویس جنگو",
  "description": "حداقل ۲۰ نویسه توضیح کامل شغل...",
  "category": 1,
  "work_mode": "HYBRID",
  "province": 8,
  "city": 40,
  "company": null,
  "duration_days": 30,
  "employment": {"employment_type": "FULL_TIME", "salary_min": 30000000, "salary_max": 50000000,
                 "required_experience_level": "MID"},
  "skills": [{"skill": 3, "is_required": true, "minimum_level": "ADVANCED"}]
}
```

Project body replaces `employment` with `project`:
`{"budget_min": 5000000, "budget_max": 10000000, "currency": "IRR", "expected_duration_days": 14, "deadline": "2027-01-20", "expected_deliverables": "..."}`.

Rules: salary/budget are required ranges (positive, max >= min); `ON_SITE`/`HYBRID` need a province
(a city implies its province); skills must exist in the active catalogue; project `deadline` must be in the future.
The owner's response adds `moderation_status`, `lifecycle_status`, `moderation_note` (the rejection reason),
`is_publicly_visible`, `duration_days`, `created_at`, `updated_at`.

## Staff moderation (`is_staff` only; others get 403)

| Method | URL | Notes |
|---|---|---|
| GET | `/admin/jobs/` | filters `moderation_status`, `lifecycle_status`, `type`. With `PENDING_REVIEW` the queue is oldest first |
| GET | `/admin/jobs/{id}/` | full post + `employer_info` (name, email, phone, join date, post counts) + `moderation_history` |
| POST | `/admin/jobs/{id}/approve/` | body `{note?}`, only from PENDING_REVIEW (409 otherwise) |
| POST | `/admin/jobs/{id}/reject/` | body `{reason}` (required, 3+ chars) |
| GET | `/admin/jobs/{id}/moderation-history/` | ordered, with actor emails |

Every state change writes an append-only `ModerationHistory` row (from, to, actor, note, time).
Django admin shows posts and history read-only so nothing can bypass the audit trail.

## Command

```bash
docker compose exec web python manage.py expire_jobs
```

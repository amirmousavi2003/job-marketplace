# API guide — Locations, Taxonomy, Resume (Phase 4)

Same conventions as Phase 3 (error envelope, Bearer auth, pagination). Live docs: `/api/docs/`.

## Design decisions (deviations from the blueprint are marked)

- **Catalogue terms.** Every name and alias of a skill / job title is one row with a globally
  unique normalized text. Normalization unifies Arabic/Persian letters (ي→ی, ك→ک), ZWNJ,
  digits and case. So "فتوشاپ", " Photoshop " and "PHOTOSHOP" can never become two entries.
- **Moderation.** Users never write to the catalogue. They submit suggestions; staff approve
  (as a new entry, or as an alias of an existing one) or reject with a reason.
- **[new app] `locations`** holds Province/City reference data (31 provinces, their capitals and
  a few large cities). It is NOT a complete city list; staff can add cities in Django admin.
- **[change] Resume names** are read from the job seeker profile (single source of truth).
  Edit them via `PATCH /profiles/job-seeker/me/`.
- **[addition] `expected_monthly_salary`** (Rial, optional) on the resume, because AI matching
  (Phase 7) needs salary expectations.
- **[change] Admin API path** is `/api/v1/admin/...` (not `/admin-api/`).
- **Item limits** (anti-abuse): educations 10, work experiences 20, skills 50, desired titles 5,
  languages 10, certificates 20, portfolio items 10.
- **Photo** is private to its owner for now. Employer access will be decided in Phase 6.

## Public reference data (no auth)

| Method | URL | Notes |
|---|---|---|
| GET | `/locations/provinces/` | `[{id,name}]`, not paginated |
| GET | `/locations/cities/?province=<id>` | `[{id,name,province}]`, not paginated |
| GET | `/categories/` | `?parent=root` for top-level only, or `?parent=<id>` |

## Skills and job titles (Bearer)

| Method | URL | Notes |
|---|---|---|
| GET | `/skills/?search=` | autocomplete, paginated. Matches names + aliases in Persian or English |
| GET | `/job-titles/?search=` | same |
| GET | `/skills/suggestions/` | my suggestions and their status |
| POST | `/skills/suggestions/` | body `{text}`. Throttled 20/hour |
| GET / POST | `/job-titles/suggestions/` | same |

Search order: exact term match, then prefix, then contains. Inactive entries are hidden.

Suggestion errors: `400` if the term already exists (message includes the existing id),
`400` if you already have 10 pending, `409 conflict` if the same term is already pending.
Status values: `PENDING`, `APPROVED`, `REJECTED` (`resulting` is filled when approved).

### Staff moderation (`is_staff` only, others get 403)

| Method | URL | Body |
|---|---|---|
| GET | `/admin/skill-suggestions/?status=PENDING` | |
| POST | `/admin/skill-suggestions/{id}/approve/` | `{}` or `{name_fa,name_en,aliases,note}` or `{existing_id}` |
| POST | `/admin/skill-suggestions/{id}/reject/` | `{note}` (required, 3+ chars) |
| same 3 | `/admin/job-title-suggestions/...` | |

Approving without names creates an entry named after the suggestion (Persian text goes to
`name_fa`, otherwise `name_en`). `existing_id` adds the suggestion as an alias of that entry.
Reviewing twice returns `409`.

## Resume (job seeker profile required, else 403)

There is no resume id in any URL; everything is the caller's own resume.

| Method | URL | Notes |
|---|---|---|
| POST | `/resumes/me/` | create once (409 if it exists). All fields optional |
| GET | `/resumes/me/` | full resume with all sections + `completeness`. 404 before creation |
| PATCH | `/resumes/me/` | scalar fields only |
| PUT / GET / DELETE | `/resumes/me/photo/` | PUT multipart field `photo` |

Scalar fields: `province`, `city` (ids; choosing a city sets its province automatically),
`contact_email`, `contact_phone`, `date_of_birth`, `introduction` (max 2000), `experience_level`
(`NO_EXPERIENCE|JUNIOR|MID|SENIOR`), `employment_status` (`EMPLOYED|UNEMPLOYED|STUDENT|SELF_EMPLOYED`),
`desired_work_modes` (list of `ON_SITE|REMOTE|HYBRID`), `expected_monthly_salary`,
`has_no_work_experience`. Read-only: `first_name`, `last_name`, `has_photo`, sections, `completeness`.

`completeness` = `{"is_complete": false, "missing": ["location","desired_job_titles","skills"]}`.
A partial resume can be saved any time; `is_complete` will gate job applications (Phase 6).
Work experience and education are optional. `has_no_work_experience=true` is rejected while
work experience entries exist, and adding an entry is rejected while it is true.

### Sections (list is a plain array, not paginated)

| Section URL (`/resumes/me/...`) | Methods | Fields |
|---|---|---|
| `educations/` | GET POST / `{id}/` GET PATCH DELETE | `degree, field_of_study, institution, start_date, end_date?` |
| `work-experiences/` | same | `job_title, company_name, start_date, end_date?, description, responsibilities` |
| `skills/` | same | `skill` (catalogue id), `level` (`BEGINNER..EXPERT`); read: `skill_name_fa/en` |
| `desired-titles/` | GET POST / `{id}/` DELETE | `job_title` (catalogue id) |
| `languages/` | same as educations | `name, proficiency` (`BASIC|CONVERSATIONAL|FLUENT|NATIVE`) |
| `certificates/` | same | `title, issuer, issue_date?, expiry_date?, credential_url` |
| `portfolio/` | same | `title, url, description` |

Rules: `end_date` must not precede `start_date` (empty `end_date` = ongoing); start dates cannot
be in the future; links must be `http(s)`; skills and job titles must come from the catalogue
(no free text, no inactive entries, no duplicates).

### Photo

JPEG/PNG/WebP, max 2 MB. The server re-encodes it to JPEG (max 800 px) and strips metadata.
`GET` needs the Bearer header, so the frontend must fetch it as a blob (a plain `<img src>`
cannot send the header).

## Demo data

```bash
docker compose exec web python manage.py seed_demo_catalogue   # 32 demo skills/titles, idempotent
```
Provinces/cities and 17 top-level categories are created automatically by migrations.

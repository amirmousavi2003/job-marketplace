# Frontend integration guide

For the React developer. Everything here is also in `docs/api/openapi.yaml` (OpenAPI 3, import it into
Postman / Insomnia, or generate a typed client). In development the live docs are at `/api/docs/`.
They are switched off in production on purpose.

Base URL: `/api/v1/`. All bodies are JSON (UTF-8, Persian is fine), except the resume photo (multipart).

## Conventions

- **Dates** are ISO 8601 (`2026-11-21`, `2026-11-21T09:30:00+03:30`), Gregorian. Convert to Jalali in the UI.
- **Money** is an integer in **Rial** (salary: per month). Projects carry a `currency` (`IRR` or `USD`).
- **Ids** are integers. **Lists** are paginated: `?page=&page_size=` (max 50) returning
  `{count, next, previous, results}`. Small reference lists (provinces, cities, categories, resume sections,
  status history) are plain arrays.
- **Errors** always have one shape, for every status code, including 404 and 500:

```json
{"error": {"code": "validation_error", "message": "Validation failed.",
           "details": {"email": ["This email is already registered."]}}}
```

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `validation_error`, `parse_error` | fix the input; `details` is per field |
| 401 | `not_authenticated`, `authentication_failed` | log in / refresh the token |
| 403 | `permission_denied` | you do not have the needed role |
| 404 | `not_found` | missing, or not yours (the API does not reveal other people's objects) |
| 409 | `conflict` | action not allowed in the current state (duplicate, wrong status) |
| 413 | `payload_too_large` | body over 1 MB (3 MB for the photo) |
| 429 | `throttled` | slow down; the message says how long |
| 500 | `server_error` | no details are leaked |

## Authentication

1. `POST /auth/register/` `{email, password, phone?}` then `POST /auth/login/` `{email, password}`
   returns `{access, refresh}`.
2. Send `Authorization: Bearer <access>` on every protected call. Access tokens live **15 minutes**.
3. When you get 401, call `POST /auth/token/refresh/` `{refresh}`. It returns a **new** pair; the old refresh
   token stops working, so always store the latest one.
4. `POST /auth/logout/` `{refresh}` revokes the refresh token.
5. Changing the password, resetting it, deactivating or erasing the account revokes **all** refresh tokens.
6. Password reset: `POST /auth/password/reset/` `{email}` (always 200). The email links to
   `{FRONTEND_URL}/reset-password?uid=...&token=...`; your page posts them to
   `/auth/password/reset/confirm/` with `new_password`. The link works once, for one hour.

Where to store tokens is your call; do not put them in URLs. CORS allows only the origins in the server's
`CORS_ALLOWED_ORIGINS`; ask the backend owner to add your dev/prod origin.

## Roles

One account can be a **job seeker**, an **employer**, or both. Roles are created by creating the profile
(`POST /profiles/job-seeker/me/`, `POST /profiles/employer/me/`). `GET /accounts/me/` returns
`roles: {is_job_seeker, is_employer, is_admin}`. Use it to decide which menus to show. The server enforces
permissions anyway: hiding a button is not security.

## Main flows

**Employer posts a job** (the post is invisible until an admin approves it)
1. `POST /jobs/employment/` or `POST /jobs/projects/` creates a `DRAFT`.
2. `POST /jobs/{id}/submit/` moves it to `PENDING_REVIEW`.
3. An admin approves (publishes) or rejects with a reason; the reason is `moderation_note` on the owner's view.
4. Editing an approved post sends it back to review. `GET /jobs/mine/` shows every state;
   `is_publicly_visible` tells whether the world can see it. Actions: deactivate, activate, renew.

**Job seeker applies**
1. Create the resume (`POST /resumes/me/`) and fill its sections. `completeness.missing` says what is
   still needed (`location`, `desired_job_titles`, `skills`).
2. Skills and job titles come from the catalogue (`GET /skills/?search=`). A missing one can be suggested
   (`POST /skills/suggestions/`); it becomes official only after admin approval.
3. `POST /jobs/{id}/applications/` for employment posts, `POST /jobs/{id}/proposals/` for projects.
   An application stores a frozen copy of the resume. Use `allowed_next_statuses` on every application /
   proposal to decide which action buttons to show.

**Recommendations.** `GET /matching/recommendations/` ranks public posts for the logged-in seeker, with
reasons. Show the `disclaimer` and the `matching.kind` honestly: it is an assistant, not a decision.
Reasons come with a stable `code` (for your own translations) and a Persian `text_fa`.

## Values you will need

| Field | Allowed values |
|---|---|
| work_mode | `ON_SITE`, `REMOTE`, `HYBRID` |
| post_type (`type` in filters) | `EMPLOYMENT`, `PROJECT` |
| employment_type | `FULL_TIME`, `PART_TIME`, `CONTRACT`, `INTERNSHIP`, `TEMPORARY` |
| experience_level / required_experience_level | `NO_EXPERIENCE`, `JUNIOR`, `MID`, `SENIOR` |
| degree / required_education | `BELOW_DIPLOMA`, `DIPLOMA`, `ASSOCIATE`, `BACHELOR`, `MASTER`, `DOCTORATE` |
| skill level / minimum_level | `BEGINNER`, `INTERMEDIATE`, `ADVANCED`, `EXPERT` |
| currency | `IRR`, `USD` |
| moderation_status | `DRAFT`, `PENDING_REVIEW`, `APPROVED`, `REJECTED` |
| lifecycle_status | `ACTIVE`, `DEACTIVATED`, `EXPIRED` |
| resume employment_status | `EMPLOYED`, `UNEMPLOYED`, `STUDENT`, `SELF_EMPLOYED` |
| language proficiency | `BASIC`, `CONVERSATIONAL`, `FLUENT`, `NATIVE` |
| application status | `PENDING`, `REVIEWING`, `INTERVIEW`, `ACCEPTED`, `REJECTED`, `WITHDRAWN` |
| proposal status | `PENDING`, `REVIEWING`, `NEGOTIATING`, `ACCEPTED`, `REJECTED`, `WITHDRAWN` |
| suggestion status | `PENDING`, `APPROVED`, `REJECTED` |

## Other notes

- Search: `GET /jobs/?q=&category=&type=&province=&city=&work_mode=&employment_type=&experience_level=&salary_min=&salary_max=&budget_min=&budget_max=&skills=1,2&skills_match=all&published_after=&ordering=`.
  Details in `docs/phase5-api-jobs-moderation.md`.
- Resume photo: `PUT /resumes/me/photo/` multipart field `photo` (JPEG/PNG/WebP, 2 MB). `GET` needs the Bearer header, so
  fetch it with `fetch` and show a blob URL; a plain `<img src>` cannot send the header.
- Rate limits exist (login 10/min, register 5/min, reset 5/hour, applications 60/hour, general 200/min
  anonymous and 600/min logged in). Handle 429 by reading the message.
- Deleting an account for good: `POST /accounts/me/erase/` `{password, confirm: true}` (irreversible).
  `POST /accounts/me/deactivate/` is the soft version.
- Per-phase detail: `docs/phase3-...` to `docs/phase7-...` list every endpoint with rules and examples.

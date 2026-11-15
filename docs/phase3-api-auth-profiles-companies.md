# API guide — Auth, Profiles, Companies (Phase 3)

Base URL: `/api/v1/`. Live docs: `/api/docs/` (Swagger).
Auth header: `Authorization: Bearer <access_token>`.

## Error format (all endpoints)

```json
{"error": {"code": "validation_error", "message": "Validation failed.",
           "details": {"email": ["This email is already registered."]}}}
```

Codes: `validation_error` 400, `not_authenticated` 401, `authentication_failed` 401,
`permission_denied` 403, `not_found` 404, `conflict` 409, `throttled` 429.

## Authentication

| Method | URL | Auth | Body | Success |
|---|---|---|---|---|
| POST | `/auth/register/` | public, throttled 5/min | `email`, `password`, `phone?` | 201 `{id,email,phone}` |
| POST | `/auth/login/` | public, throttled 10/min | `email`, `password` | 200 `{access,refresh}` |
| POST | `/auth/token/refresh/` | public | `refresh` | 200 `{access,refresh}` (rotating) |
| POST | `/auth/logout/` | refresh token in body | `refresh` | 204 |
| POST | `/auth/password/change/` | Bearer | `old_password`, `new_password` | 204 |
| POST | `/auth/password/reset/` | public, 5/hour | `email` | 200 (always) |
| POST | `/auth/password/reset/confirm/` | public, 5/hour | `uid`, `token`, `new_password` | 204 |

Notes for the frontend:
- Access token lives 15 minutes, refresh token 7 days (both configurable by env).
- Every refresh returns a NEW refresh token; the old one stops working. Always store the latest.
- Password change, password reset and account deactivation invalidate ALL refresh tokens
  (all devices). The user must log in again.
- Reset email contains `{FRONTEND_URL}/reset-password?uid=...&token=...`. The frontend page
  reads `uid` and `token` from the URL and posts them with the new password. Link lifetime: 1 hour.
- `/auth/password/reset/` answers 200 even for unknown emails (no account discovery).

Example:

```http
POST /api/v1/auth/login/
{"email": "sara@example.com", "password": "S3cure-pass-123"}

200 {"access": "eyJ...", "refresh": "eyJ..."}
```

## Account

| Method | URL | Notes |
|---|---|---|
| GET | `/accounts/me/` | `{id,email,phone,date_joined,roles}` |
| PATCH | `/accounts/me/` | only `phone` is editable |
| POST | `/accounts/me/deactivate/` | body `{password}`, 204, then login is impossible |

`roles` = `{"is_job_seeker": bool, "is_employer": bool, "is_admin": bool}`.
One account can be both job seeker and employer. Roles come from the server, never from the client.

## Profiles

| Method | URL | Notes |
|---|---|---|
| GET / POST / PATCH | `/profiles/job-seeker/me/` | fields: `first_name`, `last_name` |
| GET / POST / PATCH | `/profiles/employer/me/` | fields: `display_name`, `about` |

GET before creation: 404. POST when it already exists: 409 `conflict`.

## Companies (employer profile required, else 403)

An employer may have zero companies. A company may have several employers.

| Method | URL | Permission | Notes |
|---|---|---|---|
| GET | `/companies/` | employer | only companies I belong to, paginated, includes `my_role` |
| POST | `/companies/` | employer | creator becomes `OWNER`. `is_verified` cannot be set by clients |
| GET | `/companies/{id}/` | member | non-members get 404 |
| PATCH | `/companies/{id}/` | owner | members get 403 |
| DELETE | `/companies/{id}/` | owner | soft delete (deactivates), 204 |
| GET | `/companies/{id}/members/` | member | paginated |
| POST | `/companies/{id}/members/` | owner | body `{email}` of an existing employer account |
| DELETE | `/companies/{id}/members/{membership_id}/` | owner, or the member themself | owner cannot be removed |

Company fields: `id, name, description, website, is_verified, my_role, created_at, updated_at`.

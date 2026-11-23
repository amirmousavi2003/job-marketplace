# Security overview

## What is enforced, and how it is verified

| Area | Control | Verified by |
|---|---|---|
| Access control | Permissions are checked on the server for every endpoint. Role = existence of a profile, never a client field | **Authorization matrix test**: every route is discovered automatically; anonymous users may reach only an explicit allow-list (16 routes), and an account with no role is refused on every role-based route. A new endpoint that forgets its permission fails the build |
| Object access (IDOR) | Querysets are scoped to the caller; other people's objects answer 404 | per-feature tests (resume sections, companies, posts, applications, proposals, history, matching) |
| Mass assignment | Explicit serializer fields; owner, status, dates, moderation fields are never accepted | tests that send them and check they are ignored |
| Authentication | JWT (15 min access, rotating 7 day refresh, blacklist on rotation/logout), Argon2 password hashing, strong password validators | auth tests incl. revocation after password change / reset / deactivation / erasure |
| Rate limiting | login 10/min, register 5/min, reset 5/hour, general 200/min anonymous and 600/min logged in, plus per-feature limits. Counters live in Redis; production refuses to start without it. `X-Forwarded-For` cannot be spoofed (`DJANGO_NUM_PROXIES`) | tests incl. spoofing; manual run with 2 gunicorn workers + Redis |
| Input handling | Validation on every write, text length caps, item-count caps, http(s)-only links, JSON body cap 1 MB (413) | tests; middleware test |
| Uploads | Photo: size/pixel limits, real image check, re-encoded (metadata and hidden payloads dropped), random file name, owner-only access | upload tests incl. fake images |
| Injection | ORM only; no raw SQL, `eval`, `pickle`, `csrf_exempt` in application code | code scan |
| Secrets | Only from environment; no default `SECRET_KEY`; `.env` git-ignored; API keys never logged or returned | tests + code scan |
| Errors | One JSON shape; 500 never leaks details | tests |
| Transport/headers | Production: HTTPS redirect, secure cookies, HSTS (1 year), nosniff, frame DENY, referrer policy | `manage.py check --deploy` + live header check |
| Privacy | Resume, contact data, photo and applications are visible only to their owner and the employer who received them. Applications keep a frozen resume copy. Account erasure anonymizes and deletes personal data | privacy and visibility tests |
| Integrity | Business rules also live in the database: type-matching composite foreign keys, check constraints, partial unique indexes | DB-level tests and mutation checks |

Beyond normal tests, important rules were also checked by **mutation testing**: the rule was deliberately broken
in the code and the test suite had to fail (about 45 such checks across the phases). Gaps found this way were fixed.

## Known limitations (decide before launch)

- **No email verification** at sign-up and **no two-factor login**. Admin accounts should use strong passwords
  and the admin URL should be network-restricted.
- **Account discovery:** registration says when an email is taken; employers adding a member by email learn
  whether that email has an employer account. Both are throttled. Password reset does not leak.
- **No notifications** (email/SMS) for status changes. Password-reset email needs a working SMTP account.
- **AI and privacy.** With `local_ngram` nothing leaves your server. With `openai_compatible` the text of
  resumes (titles, skills, experience, introduction) and posts is sent to that third-party service. Tell your
  users and check the provider's terms before enabling it.
- Employers see an applicant's contact details when they apply (part of the application they chose to send).
  For project proposals, contact details are released only after acceptance.
- JWT signing uses `SECRET_KEY`. There is no per-device session list.
- Login attempts are rate-limited but not logged for audit; moderation and status history are audited.
- Hard deletion of users with data is blocked on purpose (use erasure). Backups still contain erased data until
  they rotate.

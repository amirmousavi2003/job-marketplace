# API guide — Applications and project proposals (Phase 6)

Same conventions as before (error envelope, Bearer auth, pagination). Live docs: `/api/docs/`.

## Design decisions

- **Two separate processes.** `Application` (employment posts, with a resume) and `ProjectProposal`
  (project posts, with price and days) are different tables with different statuses.
  The database refuses an application on a project post and a proposal on an employment post
  (composite foreign keys, like the detail tables of Phase 5).
- **Resume snapshot (documented choice).** When you apply, the server stores a frozen JSON copy of
  your resume in the application (`resume`, `snapshot_version: 1`). The employer always reads that
  copy, so later edits to your resume never silently change an application. The snapshot has
  contact details (resume contact email/phone, else the account's). Applying shares them with that
  employer. It leaves out date of birth and the photo.
- **Status history: separate tables** for applications and proposals (not a generic table), so each
  keeps real foreign keys and its own rules. Moderation history is a third table (Phase 5). Rows are
  append-only; the first row (`from_status` empty) is the submission.
- **Rules live in the service layer** (`applications/services.py`), the views only call them.
- **Re-applying.** You can apply again to the same post only after you withdrew. After a rejection or
  acceptance you cannot (prevents spam). Same for proposals. **[addition to your spec]** `WITHDRAWN`
  is also a status of applications.
- **Proposals and contact details.** A proposal has no resume, so the employer sees only the
  proposer's name until the proposal is `ACCEPTED`. Then the employer (only) gets `contact`.
- **Not decided for you.** Accepting an application or proposal does not close the post or reject
  the others. The employer decides what to do with the post (deactivate it).
- **Status notes** are visible to both parties: write them as a message to the other side.
- Throttle: 60 submissions per hour per user.

## Job seeker

| Method | URL | Notes |
|---|---|---|
| POST | `/jobs/{id}/applications/` | body `{cover_letter?}` (max 3000) |
| GET | `/applications/mine/` | `?status=` filter, paginated |
| POST | `/jobs/{id}/proposals/` | body `{proposed_price, estimated_days, description}` |
| GET | `/proposals/mine/` | `?status=` filter |

Application rules (checked in this order):
`404` post not public (draft, pending, rejected, deactivated, expired, unknown) |
`400` post is a project (use proposals) | `400` it is your own post |
`400` no resume, or resume incomplete (`details.missing` lists `location`, `desired_job_titles`, `skills`) |
`409` already applied.

Proposal rules: `404` not public | `400` post is an employment post (use applications) | `400` own post |
`400` invalid numbers (`proposed_price` >= 1, `estimated_days` 1 to 3650, `description` 20 to 3000 chars) |
`409` already proposed. The price may be outside the project's budget; its currency is the project's
(`currency` in the response). No complete resume is needed.

## Employer (owner of the post)

| Method | URL | Notes |
|---|---|---|
| GET | `/jobs/{id}/applications/` | `?status=`. Employment posts only (400 for projects) |
| GET | `/jobs/{id}/proposals/` | `?status=`. Project posts only (400 for employment posts) |

Other employers get `404` for posts that are not theirs; job seekers get `403`.
Lists show the applicant's name only. Open one item for the resume snapshot.

## Both parties

| Method | URL | Notes |
|---|---|---|
| GET | `/applications/{id}/`, `/proposals/{id}/` | applicant or post owner only, others `404` |
| POST | `/applications/{id}/transition/`, `/proposals/{id}/transition/` | body `{status, note?}` |
| GET | `/applications/{id}/history/`, `/proposals/{id}/history/` | `[{id,from_status,to_status,by,note,created_at}]` |

`by` is `applicant`, `employer` or `system`. Emails are never shown in history.
Every response has `allowed_next_statuses` for the caller's role: use it to show buttons.

### Status machines

Application: `PENDING -> REVIEWING | REJECTED`, `REVIEWING -> INTERVIEW | REJECTED`,
`INTERVIEW -> ACCEPTED | REJECTED` (employer). `PENDING | REVIEWING | INTERVIEW -> WITHDRAWN` (applicant).

Proposal: `PENDING -> REVIEWING | REJECTED`, `REVIEWING -> NEGOTIATING | ACCEPTED | REJECTED`,
`NEGOTIATING -> ACCEPTED | REJECTED` (employer). `PENDING | REVIEWING | NEGOTIATING -> WITHDRAWN` (applicant).

`ACCEPTED`, `REJECTED`, `WITHDRAWN` are final.
Errors: `403` if your role may never set that status (for example the applicant sets `ACCEPTED`, or the
employer sets `WITHDRAWN`); `409` if the move is not allowed from the current status (the message lists
what is allowed); `400` for an unknown status.

### Example

```json
POST /api/v1/applications/12/transition/
{"status": "INTERVIEW", "note": "لطفاً شنبه ساعت ۱۰ تماس بگیرید."}

200 {"id": 12, "status": "INTERVIEW", "allowed_next_statuses": ["ACCEPTED", "REJECTED"], "...": "..."}
```

Application detail also has `resume` (the frozen snapshot):
`personal`, `contact`, `introduction`, `experience_level`, `employment_status`, `desired_work_modes`,
`expected_monthly_salary`, `has_no_work_experience`, `desired_job_titles`, `skills`, `educations`,
`work_experiences`, `languages`, `certificates`, `portfolio_items`.

## Data protection notes

- Applications and proposals are visible only to the applicant and the owner of that post.
- Posts and job seeker profiles that have applications or proposals cannot be hard-deleted
  (use account deactivation). Django admin shows these records read-only.

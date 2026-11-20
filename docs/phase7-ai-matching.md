# AI matching (Phase 7)

Matches job seekers with posts and gives employers a reading order for applicants.
**It is assistive only.** No endpoint accepts, rejects, filters out or changes anything because of a score.

## What is real and what is not (read this first)

- The default engine is `local_ngram`: **free, offline, no key**. It measures **text overlap** (shared
  words and word fragments, with Persian normalization). It is **not a neural model**. It understands
  that "برنامه‌نویس" and "برنامه نویسی" are close; it does **not** know that "جنگو" and "Django" mean the
  same thing. The API says so: `matching.kind = "lexical"`.
- A neural engine is supported through any service with an OpenAI-style `POST /embeddings` API
  (`openai_compatible`). **I could not verify a free Iranian embeddings service**, so none is assumed.
  If you get a key from a gateway, ask whether it offers `/v1/embeddings`, then fill the 4 settings below.
- If the AI service is not configured or is down, scores are computed from structured data only and the
  response says `semantic_used: false` with a reason. Nothing is ever shown as AI-generated when it was not.
- Scores are a rough compatibility indicator, not scientifically precise. Every response carries a disclaimer.

## Pipeline

1. **Extract** structured features from a resume (live resume, or the frozen snapshot of an application)
   and from a post. 2. **Normalize** (Persian/Arabic letters, ZWNJ, digits). 3. **Embed** the texts through the
   provider (vectors are cached by text hash, per provider and model). 4. **Cosine similarity**.
5. **Structured compatibility** per factor. 6. **Hard constraints** (cap the score, never remove a post).
7. **Combine** with configurable weights. 8. **Explain** with coded reasons (`code`, `polarity`, `params`,
Persian `text_fa`) so the frontend can localize.

Structured factors (weights in `settings.MATCHING["WEIGHTS"]`; factors that do not apply are left out and
the rest are renormalized): skills 0.40, title 0.15, experience 0.10, education 0.05, work mode 0.10,
location 0.10, salary 0.10. Experience, education and salary apply to employment posts only
(resumes have no budget expectation, so project budgets are not scored).

Hard constraints (score capped at 40, shown as `HARD_CONSTRAINT_WARNING`): none of the required skills
matched; on-site post in another province; experience two levels or more below the requirement.

Final score = structured, mixed with the text similarity when available (`lexical` 20%, `neural` 35%).
Unknown data is never treated as a mismatch (for example a resume without education is not penalized).

## Settings (`.env`)

```
AI_EMBEDDING_PROVIDER=local_ngram        # local_ngram (default) | openai_compatible | none
# only for openai_compatible:
AI_EMBEDDING_API_URL=https://example.ir/v1     # https required (http only for localhost)
AI_EMBEDDING_API_KEY=...
AI_EMBEDDING_MODEL=...
```

Keys live only in the environment. They are never logged, stored or returned by the API
(`/matching/status/` shows provider, model and kind only). An incomplete configuration prints a startup
warning (`matching.W001`) and matching falls back to structured scoring.
The older `EMBEDDING_*` lines in an old `.env` are ignored.

## API (Bearer token)

| Method | URL | Who | Notes |
|---|---|---|---|
| GET | `/matching/status/` | any user | engine info + disclaimer |
| GET | `/matching/recommendations/` | job seeker | public posts ranked for your resume. `?type=`, `?min_score=`, paging. Needs a resume |
| GET | `/matching/jobs/{id}/` | job seeker | your score for one public post: `factors`, `all_reasons`, `disclaimer` |
| POST | `/matching/recompute/` | job seeker | refresh now (20/hour). `semantic`: `used`, `pending` or `unavailable` |
| GET | `/matching/jobs/{id}/candidates/` | owner of an employment post | applicants in suggested reading order |

Candidates are scored from what each applicant **submitted** (the frozen snapshot), are not stored,
show names only (no contact details) and everyone who applied is listed.

Row example:

```json
{"score": 82, "semantic_used": true, "flags": [],
 "reasons": [{"code": "SKILL_OVERLAP_STRONG", "polarity": "positive", "params": {"matched": 1, "total": 1},
              "text_fa": "هم‌پوشانی قوی مهارت‌ها"}],
 "post": { "...": "public post" }}
```

`reasons` in lists = the 3 most important (warnings first). Codes: `SKILL_OVERLAP_*`, `MISSING_REQUIRED_SKILLS`,
`TITLE_*`, `EXPERIENCE_*`, `EDUCATION_*`, `WORK_MODE_*`, `LOCATION_*`, `SALARY_*`, `SEMANTIC_*`
(`SIMILAR`, `RELATED`, `DISTANT`, `UNAVAILABLE`, `PENDING`), `HARD_CONSTRAINT_WARNING`, `INSUFFICIENT_DATA`.

Stored results: table `AIMatch` (seeker, post, score, factors, explanation, provider, model, version,
time). A row is recomputed only when an input changes (resume, post, provider/model or scoring settings).

## Background processing

Network embeddings never block a web request: they are queued (Celery) and the response says
`SEMANTIC_PENDING` until the vectors exist. A newly approved post gets its vector prepared automatically.
The cheap local engine runs inline.

```bash
docker compose --profile async up -d      # starts worker + beat
```
Also set `CELERY_TASK_ALWAYS_EAGER=False` in `.env`. Without it (default in development) tasks run inline.
`beat` also runs `expire_jobs` every day at 03:00 (Tehran), so you no longer need a cron for it.
Backfill vectors for existing posts: `python manage.py compute_embeddings`.

## Data protection

- A seeker only gets scores for their own resume; employers only for people who applied to their post.
- Matches never trigger status changes, notifications or visibility changes.
- Cached vectors are stored by text hash. Old rows are harmless; changing the model creates new rows.

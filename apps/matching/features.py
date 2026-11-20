"""Step 1-2 of the pipeline: extract structured features and normalize them.

Both a live resume and a frozen application snapshot produce the same `ResumeFeatures`, so an
employer ranking applicants sees exactly what the applicant submitted."""

import hashlib
import json
from dataclasses import asdict, dataclass

from apps.common.text import normalize_text

EXPERIENCE_RANK = {"NO_EXPERIENCE": 0, "JUNIOR": 1, "MID": 2, "SENIOR": 3}
DEGREE_RANK = {
    "BELOW_DIPLOMA": 0,
    "DIPLOMA": 1,
    "ASSOCIATE": 2,
    "BACHELOR": 3,
    "MASTER": 4,
    "DOCTORATE": 5,
}
SKILL_RANK = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2, "EXPERT": 3}
MAX_TEXT_CHARS = 3000


def _label(name_fa: str, name_en: str) -> str:
    return name_fa or name_en


@dataclass(frozen=True)
class ResumeFeatures:
    skills: tuple  # ((skill_id, label, level), ...) sorted by id
    title_terms: tuple  # normalized desired job titles (fa and en names)
    experience_level: str
    highest_degree: int  # -1 when no education is listed
    work_modes: tuple
    province: str  # normalized name, "" if unknown
    city: str
    expected_salary: int | None
    text_parts: tuple  # inputs of the embedding text

    def text(self) -> str:
        return normalize_text(" ؛ ".join(p for p in self.text_parts if p))[:MAX_TEXT_CHARS]

    def digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True)
class PostFeatures:
    post_id: int
    post_type: str
    title: str
    title_norm: str
    required_skills: tuple  # ((skill_id, label, min_level), ...)
    optional_skills: tuple
    work_mode: str
    province: str
    city: str
    required_experience: str
    required_degree: int  # -1 when not required
    salary_min: int | None
    salary_max: int | None
    text_parts: tuple

    def text(self) -> str:
        return normalize_text(" ؛ ".join(p for p in self.text_parts if p))[:MAX_TEXT_CHARS]

    def digest(self) -> str:
        return _digest(asdict(self))


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _build_resume_features(
    *,
    skills,
    titles,
    experience_level,
    degrees,
    work_modes,
    province,
    city,
    expected_salary,
    introduction,
    experiences,
    education_fields,
) -> ResumeFeatures:
    skill_rows = tuple(sorted((sid, label, level) for sid, label, level in skills))
    title_terms = tuple(sorted({normalize_text(t) for t in titles if t}))
    ranks = [DEGREE_RANK[d] for d in degrees if d in DEGREE_RANK]
    return ResumeFeatures(
        skills=skill_rows,
        title_terms=title_terms,
        experience_level=experience_level or "",
        highest_degree=max(ranks) if ranks else -1,
        work_modes=tuple(sorted(set(work_modes))),
        province=normalize_text(province or ""),
        city=normalize_text(city or ""),
        expected_salary=expected_salary,
        text_parts=(
            "عناوین شغلی: " + "، ".join(title_terms),
            "مهارت‌ها: " + "، ".join(label for _, label, _ in skill_rows),
            *experiences,
            *education_fields,
            introduction or "",
        ),
    )


def resume_features(resume) -> ResumeFeatures:
    """From a live Resume loaded with resumes.selectors.resume_queryset()."""
    titles = []
    for link in resume.desired_job_titles.all():
        titles += [link.job_title.name_fa, link.job_title.name_en]
    return _build_resume_features(
        skills=[
            (link.skill_id, _label(link.skill.name_fa, link.skill.name_en), link.level)
            for link in resume.resume_skills.all()
        ],
        titles=titles,
        experience_level=resume.experience_level,
        degrees=[e.degree for e in resume.educations.all()],
        work_modes=resume.desired_work_modes,
        province=resume.province.name if resume.province else "",
        city=resume.city.name if resume.city else "",
        expected_salary=resume.expected_monthly_salary,
        introduction=resume.introduction,
        experiences=[
            f"{w.job_title} {(w.description or '')[:200]}" for w in resume.work_experiences.all()
        ],
        education_fields=[e.field_of_study for e in resume.educations.all()],
    )


def snapshot_features(snapshot: dict) -> ResumeFeatures:
    """From the frozen resume stored on an application (applications.snapshot)."""
    personal = snapshot.get("personal", {})
    titles = []
    for title in snapshot.get("desired_job_titles", []):
        titles += [title.get("name_fa", ""), title.get("name_en", "")]
    return _build_resume_features(
        skills=[
            (s["skill_id"], _label(s.get("name_fa", ""), s.get("name_en", "")), s["level"])
            for s in snapshot.get("skills", [])
        ],
        titles=titles,
        experience_level=snapshot.get("experience_level", ""),
        degrees=[e["degree"] for e in snapshot.get("educations", [])],
        work_modes=snapshot.get("desired_work_modes", []),
        province=personal.get("province") or "",
        city=personal.get("city") or "",
        expected_salary=snapshot.get("expected_monthly_salary"),
        introduction=snapshot.get("introduction", ""),
        experiences=[
            f"{w['job_title']} {(w.get('description') or '')[:200]}"
            for w in snapshot.get("work_experiences", [])
        ],
        education_fields=[e["field_of_study"] for e in snapshot.get("educations", [])],
    )


def post_features(post) -> PostFeatures:
    """From a JobPost loaded with jobs.selectors.base_queryset()."""
    required, optional = [], []
    for link in post.post_skills.all():
        row = (link.skill_id, _label(link.skill.name_fa, link.skill.name_en), link.minimum_level)
        (required if link.is_required else optional).append(row)
    employment = getattr(post, "employment_detail", None)
    degree = (employment.required_education if employment else "") or ""
    category = post.category
    return PostFeatures(
        post_id=post.pk,
        post_type=post.post_type,
        title=post.title,
        title_norm=normalize_text(post.title),
        required_skills=tuple(sorted(required)),
        optional_skills=tuple(sorted(optional)),
        work_mode=post.work_mode,
        province=normalize_text(post.province.name if post.province else ""),
        city=normalize_text(post.city.name if post.city else ""),
        required_experience=(employment.required_experience_level if employment else "") or "",
        required_degree=DEGREE_RANK.get(degree, -1),
        salary_min=employment.salary_min if employment else None,
        salary_max=employment.salary_max if employment else None,
        text_parts=(
            post.title,
            f"{category.name_fa} {category.name_en}",
            "مهارت‌ها: " + "، ".join(label for _, label, _ in (*required, *optional)),
            post.description[:1500],
        ),
    )

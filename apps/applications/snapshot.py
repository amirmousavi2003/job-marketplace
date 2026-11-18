"""Frozen copy of a resume, stored on an Application at submission time.

Included: what an employer needs to judge a candidate. Left out on purpose: date of birth and
the profile photo (not needed to review a candidate; photo access is a separate decision)."""

from django.utils import timezone

SNAPSHOT_VERSION = 1


def _name(obj, fa="name_fa", en="name_en"):
    return {"name_fa": getattr(obj, fa), "name_en": getattr(obj, en)}


def build_resume_snapshot(resume) -> dict:
    """`resume` must come from resumes.selectors.resume_queryset() (relations prefetched)."""
    profile = resume.job_seeker
    user = profile.user
    return {
        "version": SNAPSHOT_VERSION,
        "captured_at": timezone.now().isoformat(),
        "personal": {
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "province": resume.province.name if resume.province else None,
            "city": resume.city.name if resume.city else None,
        },
        # Applying shares these contact details with the employer who receives the application.
        "contact": {
            "email": resume.contact_email or user.email,
            "phone": resume.contact_phone or user.phone or "",
        },
        "introduction": resume.introduction,
        "experience_level": resume.experience_level,
        "employment_status": resume.employment_status,
        "desired_work_modes": list(resume.desired_work_modes),
        "expected_monthly_salary": resume.expected_monthly_salary,
        "has_no_work_experience": resume.has_no_work_experience,
        "desired_job_titles": [
            {"id": link.job_title_id, **_name(link.job_title)}
            for link in resume.desired_job_titles.all()
        ],
        "skills": [
            {"skill_id": link.skill_id, **_name(link.skill), "level": link.level}
            for link in resume.resume_skills.all()
        ],
        "educations": [
            {
                "degree": e.degree,
                "field_of_study": e.field_of_study,
                "institution": e.institution,
                "start_date": e.start_date.isoformat(),
                "end_date": e.end_date.isoformat() if e.end_date else None,
            }
            for e in resume.educations.all()
        ],
        "work_experiences": [
            {
                "job_title": w.job_title,
                "company_name": w.company_name,
                "start_date": w.start_date.isoformat(),
                "end_date": w.end_date.isoformat() if w.end_date else None,
                "description": w.description,
                "responsibilities": w.responsibilities,
            }
            for w in resume.work_experiences.all()
        ],
        "languages": [
            {"name": lang.name, "proficiency": lang.proficiency} for lang in resume.languages.all()
        ],
        "certificates": [
            {
                "title": c.title,
                "issuer": c.issuer,
                "issue_date": c.issue_date.isoformat() if c.issue_date else None,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                "credential_url": c.credential_url,
            }
            for c in resume.certificates.all()
        ],
        "portfolio_items": [
            {"title": p.title, "url": p.url, "description": p.description}
            for p in resume.portfolio_items.all()
        ],
    }

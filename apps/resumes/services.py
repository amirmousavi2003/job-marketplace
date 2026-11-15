from django.db import transaction
from rest_framework.exceptions import ValidationError

from .images import process_profile_image

# Anti-abuse caps (documented in the API guide).
MAX_ITEMS = {
    "educations": 10,
    "work_experiences": 20,
    "resume_skills": 50,
    "desired_job_titles": 5,
    "languages": 10,
    "certificates": 20,
    "portfolio_items": 10,
}


def completeness(resume) -> dict:
    """What is still missing before the resume can be used to apply for jobs.
    Uses prefetched relations when available (no extra queries)."""
    missing = []
    if not resume.province_id or not resume.city_id:
        missing.append("location")
    if not len(resume.desired_job_titles.all()):
        missing.append("desired_job_titles")
    if not len(resume.resume_skills.all()):
        missing.append("skills")
    return {"is_complete": not missing, "missing": missing}


def check_item_limit(resume, relation: str) -> None:
    limit = MAX_ITEMS[relation]
    if getattr(resume, relation).count() >= limit:
        raise ValidationError({"detail": f"You can add at most {limit} items to this section."})


@transaction.atomic
def set_photo(resume, uploaded) -> None:
    new_file = process_profile_image(uploaded)
    old = resume.photo.name if resume.photo else None
    resume.photo.save(new_file.name, new_file, save=False)
    resume.save(update_fields=["photo", "updated_at"])
    if old:
        resume.photo.storage.delete(old)


@transaction.atomic
def remove_photo(resume) -> None:
    if resume.photo:
        name = resume.photo.name
        resume.photo = None
        resume.save(update_fields=["photo", "updated_at"])
        resume.photo.storage.delete(name)

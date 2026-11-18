from django.db.models import Prefetch

from .models import DesiredJobTitle, Resume, ResumeSkill


def resume_queryset():
    """Resumes with every section loaded in a fixed, small number of queries."""
    return Resume.objects.select_related("job_seeker", "province", "city").prefetch_related(
        Prefetch("desired_job_titles", DesiredJobTitle.objects.select_related("job_title")),
        Prefetch("resume_skills", ResumeSkill.objects.select_related("skill")),
        "educations",
        "work_experiences",
        "languages",
        "certificates",
        "portfolio_items",
    )

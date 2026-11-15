from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("educations", views.EducationViewSet, basename="resume-education")
router.register("work-experiences", views.WorkExperienceViewSet, basename="resume-work-experience")
router.register("skills", views.ResumeSkillViewSet, basename="resume-skill")
router.register("desired-titles", views.DesiredJobTitleViewSet, basename="resume-desired-title")
router.register("languages", views.LanguageViewSet, basename="resume-language")
router.register("certificates", views.CertificateViewSet, basename="resume-certificate")
router.register("portfolio", views.PortfolioItemViewSet, basename="resume-portfolio")

urlpatterns = [
    path("me/", views.ResumeView.as_view(), name="resume"),
    path("me/photo/", views.ResumePhotoView.as_view(), name="resume-photo"),
    path("me/", include(router.urls)),
]

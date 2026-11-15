from django.urls import path

from . import views

urlpatterns = [
    path("job-seeker/me/", views.JobSeekerProfileView.as_view(), name="profile-job-seeker"),
    path("employer/me/", views.EmployerProfileView.as_view(), name="profile-employer"),
]

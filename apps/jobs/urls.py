from django.urls import path

from . import views

urlpatterns = [
    path("", views.PublicJobListView.as_view(), name="job-list"),
    path("employment/", views.EmploymentListCreateView.as_view(), name="job-employment"),
    path("projects/", views.ProjectListCreateView.as_view(), name="job-projects"),
    path("mine/", views.MyPostsView.as_view(), name="job-mine"),
    path("<int:pk>/", views.JobPostDetailView.as_view(), name="job-detail"),
    path("<int:pk>/submit/", views.SubmitView.as_view(), name="job-submit"),
    path("<int:pk>/deactivate/", views.DeactivateView.as_view(), name="job-deactivate"),
    path("<int:pk>/activate/", views.ActivateView.as_view(), name="job-activate"),
    path("<int:pk>/renew/", views.RenewView.as_view(), name="job-renew"),
]

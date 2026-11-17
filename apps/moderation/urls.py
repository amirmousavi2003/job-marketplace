from django.urls import path

from . import views

admin_urlpatterns = [
    path("jobs/", views.AdminJobListView.as_view(), name="admin-job-list"),
    path("jobs/<int:pk>/", views.AdminJobDetailView.as_view(), name="admin-job-detail"),
    path("jobs/<int:pk>/approve/", views.AdminJobApproveView.as_view(), name="admin-job-approve"),
    path("jobs/<int:pk>/reject/", views.AdminJobRejectView.as_view(), name="admin-job-reject"),
    path(
        "jobs/<int:pk>/moderation-history/",
        views.AdminModerationHistoryView.as_view(),
        name="admin-job-history",
    ),
]

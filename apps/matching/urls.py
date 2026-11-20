from django.urls import path

from . import views

urlpatterns = [
    path("status/", views.StatusView.as_view(), name="matching-status"),
    path("recommendations/", views.RecommendationsView.as_view(), name="matching-recommendations"),
    path("recompute/", views.RecomputeView.as_view(), name="matching-recompute"),
    path("jobs/<int:pk>/", views.JobMatchView.as_view(), name="matching-job"),
    path("jobs/<int:pk>/candidates/", views.CandidatesView.as_view(), name="matching-candidates"),
]

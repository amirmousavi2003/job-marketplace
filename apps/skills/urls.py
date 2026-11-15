from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.JobCategoryListView.as_view(), name="category-list"),
    path("skills/", views.SkillListView.as_view(), name="skill-list"),
    path("skills/suggestions/", views.MySkillSuggestionsView.as_view(), name="skill-suggestions"),
    path("job-titles/", views.JobTitleListView.as_view(), name="job-title-list"),
    path(
        "job-titles/suggestions/",
        views.MyJobTitleSuggestionsView.as_view(),
        name="job-title-suggestions",
    ),
]

admin_urlpatterns = [
    path(
        "skill-suggestions/",
        views.AdminSkillSuggestionListView.as_view(),
        name="admin-skill-suggestions",
    ),
    path(
        "skill-suggestions/<int:pk>/approve/",
        views.AdminSkillSuggestionApproveView.as_view(),
        name="admin-skill-suggestion-approve",
    ),
    path(
        "skill-suggestions/<int:pk>/reject/",
        views.AdminSkillSuggestionRejectView.as_view(),
        name="admin-skill-suggestion-reject",
    ),
    path(
        "job-title-suggestions/",
        views.AdminJobTitleSuggestionListView.as_view(),
        name="admin-job-title-suggestions",
    ),
    path(
        "job-title-suggestions/<int:pk>/approve/",
        views.AdminJobTitleSuggestionApproveView.as_view(),
        name="admin-job-title-suggestion-approve",
    ),
    path(
        "job-title-suggestions/<int:pk>/reject/",
        views.AdminJobTitleSuggestionRejectView.as_view(),
        name="admin-job-title-suggestion-reject",
    ),
]

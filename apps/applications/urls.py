from django.urls import path

from . import views

urlpatterns = [
    # applications (employment posts)
    path(
        "jobs/<int:post_id>/applications/",
        views.PostApplicationsView.as_view(),
        name="post-applications",
    ),
    path("applications/mine/", views.MyApplicationsView.as_view(), name="my-applications"),
    path(
        "applications/<int:pk>/", views.ApplicationDetailView.as_view(), name="application-detail"
    ),
    path(
        "applications/<int:pk>/transition/",
        views.ApplicationTransitionView.as_view(),
        name="application-transition",
    ),
    path(
        "applications/<int:pk>/history/",
        views.ApplicationHistoryView.as_view(),
        name="application-history",
    ),
    # project proposals (project posts)
    path("jobs/<int:post_id>/proposals/", views.PostProposalsView.as_view(), name="post-proposals"),
    path("proposals/mine/", views.MyProposalsView.as_view(), name="my-proposals"),
    path("proposals/<int:pk>/", views.ProposalDetailView.as_view(), name="proposal-detail"),
    path(
        "proposals/<int:pk>/transition/",
        views.ProposalTransitionView.as_view(),
        name="proposal-transition",
    ),
    path(
        "proposals/<int:pk>/history/", views.ProposalHistoryView.as_view(), name="proposal-history"
    ),
]

from django.urls import path

from . import views

urlpatterns = [
    path("", views.CompanyListCreateView.as_view(), name="company-list"),
    path("<int:pk>/", views.CompanyDetailView.as_view(), name="company-detail"),
    path("<int:company_id>/members/", views.CompanyMembersView.as_view(), name="company-members"),
    path(
        "<int:company_id>/members/<int:membership_id>/",
        views.CompanyMemberDetailView.as_view(),
        name="company-member-detail",
    ),
]

from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MeView.as_view(), name="account-me"),
    path("me/deactivate/", views.DeactivateAccountView.as_view(), name="account-deactivate"),
]

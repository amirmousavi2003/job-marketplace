from django.urls import path

from . import views

urlpatterns = [
    path("me/erase/", views.EraseAccountView.as_view(), name="account-erase"),
]

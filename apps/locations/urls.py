from django.urls import path

from . import views

urlpatterns = [
    path("provinces/", views.ProvinceListView.as_view(), name="province-list"),
    path("cities/", views.CityListView.as_view(), name="city-list"),
]

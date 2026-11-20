from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.moderation import urls as moderation_urls
from apps.skills import urls as skills_urls

api_v1 = [
    path("", include("apps.common.urls")),
    path("auth/", include("apps.accounts.auth_urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("profiles/", include("apps.profiles.urls")),
    path("companies/", include("apps.companies.urls")),
    path("locations/", include("apps.locations.urls")),
    path("resumes/", include("apps.resumes.urls")),
    path("jobs/", include("apps.jobs.urls")),
    path("", include("apps.applications.urls")),
    path("matching/", include("apps.matching.urls")),
    path("admin/", include((moderation_urls.admin_urlpatterns, "admin-moderation"))),
    path("", include("apps.skills.urls")),
    path("admin/", include((skills_urls.admin_urlpatterns, "admin-api"))),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

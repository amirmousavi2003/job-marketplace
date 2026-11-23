from django.core.exceptions import ImproperlyConfigured

from .base import *

# Rate limiting stores its counters in the cache. Without a cache shared by every worker process
# each worker counts alone, so the limits silently become several times weaker. Refuse to start.
if not env("REDIS_URL", default=""):
    raise ImproperlyConfigured(
        "REDIS_URL is required in production: rate limiting needs a cache shared by all workers."
    )

DEBUG = False
ENABLE_API_DOCS = env.bool("DJANGO_ENABLE_API_DOCS", default=False)
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# HSTS preload is deliberately NOT enabled: it is a one-way commitment for the whole domain.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

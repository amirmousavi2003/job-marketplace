from .base import *

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-for-production"  # noqa: S105
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Fast hasher: tests only.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
ENABLE_API_DOCS = True
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **{k: "1000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},
        # the whole test run shares one fake client address
        "anon": "1000000/min",
        "user": "1000000/min",
    },
}

from .base import *

DEBUG = True
ENABLE_API_DOCS = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Dev default: run Celery tasks inline so no worker is needed (emails print in the web log).
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)

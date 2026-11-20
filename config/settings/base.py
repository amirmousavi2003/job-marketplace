"""Base settings shared by all environments. Secrets come from the environment only."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # optional; real env vars win

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
]
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.profiles",
    "apps.companies",
    "apps.locations",
    "apps.skills",
    "apps.resumes",
    "apps.jobs",
    "apps.moderation",
    "apps.applications",
    "apps.matching",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT_SECONDS", default=3600)
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@jobmarket.local")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10/min",
        "auth_register": "5/min",
        "auth_password_reset": "5/hour",
        "suggestions": "20/hour",
        "job_create": "30/hour",
        "apply": "60/hour",
        "matching_recompute": "20/hour",
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Job Marketplace API",
    "DESCRIPTION": "Employment and freelance project marketplace for Iran.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Stable, readable names for enums in the generated schema / frontend clients.
    "ENUM_NAME_OVERRIDES": {
        "ExperienceLevelEnum": "apps.common.choices.ExperienceLevel.choices",
        "WorkModeEnum": "apps.common.choices.WorkMode.choices",
        "DegreeLevelEnum": "apps.common.choices.DegreeLevel.choices",
        "SkillLevelEnum": "apps.common.choices.SkillLevel.choices",
        "PostTypeEnum": "apps.jobs.models.PostType.choices",
        "ModerationStatusEnum": "apps.jobs.models.ModerationStatus.choices",
        "LifecycleStatusEnum": "apps.jobs.models.LifecycleStatus.choices",
        "EmploymentTypeEnum": "apps.jobs.models.EmploymentType.choices",
        "CurrencyEnum": "apps.jobs.models.Currency.choices",
        "ApplicationStatusEnum": "apps.applications.models.ApplicationStatus.choices",
        "ProposalStatusEnum": "apps.applications.models.ProposalStatus.choices",
        "SuggestionStatusEnum": "apps.skills.models.SuggestionStatus.choices",
        "EmploymentStatusEnum": "apps.resumes.models.EmploymentStatus.choices",
        "LanguageLevelEnum": "apps.resumes.models.LanguageLevel.choices",
    },
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL or "cache+memory://")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "expire-overdue-job-posts": {
        "task": "apps.jobs.tasks.expire_overdue_posts",
        "schedule": crontab(hour=3, minute=0),
    },
}

# ---- AI matching -----------------------------------------------------------------------
# AI_EMBEDDING_PROVIDER: "local_ngram" (default: offline, no key, lexical similarity),
# "openai_compatible" (any service with an OpenAI-style /embeddings API) or "none".
AI_EMBEDDING_PROVIDER = env("AI_EMBEDDING_PROVIDER", default="local_ngram")
AI_EMBEDDING_API_URL = env("AI_EMBEDDING_API_URL", default="")  # e.g. https://host/v1
AI_EMBEDDING_API_KEY = env("AI_EMBEDDING_API_KEY", default="")
AI_EMBEDDING_MODEL = env("AI_EMBEDDING_MODEL", default="")
AI_EMBEDDING_TIMEOUT_SECONDS = env.int("AI_EMBEDDING_TIMEOUT_SECONDS", default=20)
AI_EMBEDDING_BATCH_SIZE = env.int("AI_EMBEDDING_BATCH_SIZE", default=16)

MATCHING = {
    "MAX_CANDIDATES": 200,  # posts scored per recommendation request
    "HARD_CONSTRAINT_CAP": 40,  # a hard-constraint violation caps the score here (never rejects)
    # relative weights of structured factors; factors that do not apply are left out
    "WEIGHTS": {
        "skills": 0.40,
        "title": 0.15,
        "experience": 0.10,
        "education": 0.05,
        "work_mode": 0.10,
        "location": 0.10,
        "salary": 0.10,
    },
    # share of the final score given to text similarity, by provider kind
    "SEMANTIC_WEIGHT": {"lexical": 0.20, "neural": 0.35},
    # cosine values mapped to 0..1 (below low = 0, above high = 1)
    "SEMANTIC_RANGE": {"lexical": (0.15, 0.55), "neural": (0.30, 0.85)},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

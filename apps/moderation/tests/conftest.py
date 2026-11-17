# Reuse the job fixtures (posts, staff user, categories) in moderation tests.
from apps.jobs.tests.conftest import category, make_post, payloads, shiraz, staff  # noqa: F401

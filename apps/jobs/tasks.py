from celery import shared_task

from . import services


@shared_task
def expire_overdue_posts() -> int:
    return services.expire_overdue_posts()

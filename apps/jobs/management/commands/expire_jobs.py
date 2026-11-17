from django.core.management.base import BaseCommand

from apps.jobs.services import expire_overdue_posts


class Command(BaseCommand):
    help = "Mark approved posts past their expiry date as EXPIRED (schedule with cron/Celery beat)."

    def handle(self, *args, **options):
        count = expire_overdue_posts()
        self.stdout.write(self.style.SUCCESS(f"{count} post(s) expired."))

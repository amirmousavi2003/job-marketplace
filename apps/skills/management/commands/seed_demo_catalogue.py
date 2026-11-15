from django.core.management.base import BaseCommand
from rest_framework.exceptions import ValidationError

from apps.skills import services
from apps.skills.data import DEMO_JOB_TITLES, DEMO_SKILLS


class Command(BaseCommand):
    help = "Create a small demo catalogue of skills and job titles (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for kind, rows in ((services.SKILL, DEMO_SKILLS), (services.JOB_TITLE, DEMO_JOB_TITLES)):
            for name_fa, name_en, aliases in rows:
                if services.find_entry(kind, name_fa) or services.find_entry(kind, name_en):
                    continue
                try:
                    services.create_entry(kind, name_fa=name_fa, name_en=name_en, aliases=aliases)
                    created += 1
                except ValidationError as exc:
                    self.stderr.write(f"Skipped {name_fa}: {exc.detail}")
        self.stdout.write(self.style.SUCCESS(f"Demo catalogue ready ({created} new entries)."))

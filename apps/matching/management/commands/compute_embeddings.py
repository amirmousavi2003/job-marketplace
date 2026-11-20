from django.core.management.base import BaseCommand

from apps.matching.providers import EmbeddingError, get_provider
from apps.matching.tasks import embed_visible_posts


class Command(BaseCommand):
    help = "Create text vectors for all public posts with the configured provider (idempotent)."

    def handle(self, *args, **options):
        provider = get_provider()
        if not provider.available:
            self.stdout.write(f"Provider '{provider.name}' produces no vectors: {provider.reason}")
            return
        try:
            created = embed_visible_posts()
        except EmbeddingError as exc:
            self.stderr.write(f"Embedding failed: {exc}")
            return
        self.stdout.write(
            self.style.SUCCESS(f"{created} new vector(s) with {provider.name}/{provider.model}.")
        )

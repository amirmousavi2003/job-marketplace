from django.conf import settings
from django.db import models

from apps.jobs.models import JobPost, ModerationStatus


class ModerationHistory(models.Model):
    """Append-only audit trail of every moderation-state change of a post."""

    job_post = models.ForeignKey(
        JobPost, on_delete=models.CASCADE, related_name="moderation_history"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_status = models.CharField(max_length=15, choices=ModerationStatus.choices)
    to_status = models.CharField(max_length=15, choices=ModerationStatus.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "moderation history"
        indexes = [models.Index(fields=["job_post", "id"], name="moderation_post_idx")]

    def __str__(self):
        return f"{self.job_post_id}: {self.from_status} -> {self.to_status}"

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.jobs.models import JobPost
from apps.profiles.models import JobSeekerProfile


class AIMatch(models.Model):
    """Latest compatibility score of one job seeker's resume with one job post.

    Assistive information only: nothing in the system reads this to accept, reject or rank
    anyone out. It is derived data and is recomputed whenever any input changes (`inputs_hash`)."""

    job_seeker = models.ForeignKey(
        JobSeekerProfile, on_delete=models.CASCADE, related_name="matches"
    )
    job_post = models.ForeignKey(JobPost, on_delete=models.CASCADE, related_name="matches")
    score = models.PositiveSmallIntegerField()
    factors = models.JSONField(default=dict)
    explanation = models.JSONField(default=list)
    flags = models.JSONField(default=list)
    provider = models.CharField(max_length=30)  # "none" when no semantic part was used
    model_name = models.CharField(max_length=100, blank=True)
    semantic_used = models.BooleanField(default=False)
    scoring_version = models.CharField(max_length=10)
    inputs_hash = models.CharField(max_length=64)
    computed_at = models.DateTimeField()

    class Meta:
        ordering = ["-score", "-id"]
        verbose_name = "AI match"
        constraints = [
            models.UniqueConstraint(
                fields=["job_seeker", "job_post"], name="matching_one_per_pair"
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0) & Q(score__lte=100), name="matching_score_0_100"
            ),
        ]
        indexes = [models.Index(fields=["job_seeker", "-score"], name="matching_seeker_score_idx")]

    def __str__(self):
        return f"{self.job_seeker_id} x {self.job_post_id}: {self.score}"


class EmbeddingCache(TimeStampedModel):
    """Vector of one text, stored by the hash of the text (content-addressed) and scoped to the
    provider + model that produced it. Changed text or a new model simply gets a new row."""

    provider = models.CharField(max_length=30)
    model = models.CharField(max_length=100)
    text_hash = models.CharField(max_length=64)
    vector = ArrayField(models.FloatField())

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "model", "text_hash"], name="matching_unique_embedding"
            )
        ]

    def __str__(self):
        return f"{self.provider}/{self.model}:{self.text_hash[:8]}"

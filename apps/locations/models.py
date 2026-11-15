from django.db import models


class Province(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class City(models.Model):
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="cities")
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "cities"
        constraints = [
            models.UniqueConstraint(fields=["province", "name"], name="locations_unique_city")
        ]

    def __str__(self):
        return f"{self.name} ({self.province})"

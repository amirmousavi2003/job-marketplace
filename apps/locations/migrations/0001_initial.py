import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Province",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                (
                    "province",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cities",
                        to="locations.province",
                    ),
                ),
            ],
            options={"verbose_name_plural": "cities", "ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="city",
            constraint=models.UniqueConstraint(fields=("province", "name"), name="locations_unique_city"),
        ),
    ]

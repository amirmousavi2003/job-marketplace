from django.db import migrations

from apps.skills.data import CATEGORIES


def seed(apps, schema_editor):
    JobCategory = apps.get_model("skills", "JobCategory")
    for order, (name_fa, name_en, slug) in enumerate(CATEGORIES, start=1):
        JobCategory.objects.get_or_create(
            slug=slug, defaults={"name_fa": name_fa, "name_en": name_en, "sort_order": order}
        )


class Migration(migrations.Migration):
    dependencies = [("skills", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

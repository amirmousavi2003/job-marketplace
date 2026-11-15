from django.db import migrations

from apps.locations.data import PROVINCES


def seed(apps, schema_editor):
    Province = apps.get_model("locations", "Province")
    City = apps.get_model("locations", "City")
    for province_name, cities in PROVINCES.items():
        province, _ = Province.objects.get_or_create(name=province_name)
        for city_name in cities:
            City.objects.get_or_create(province=province, name=city_name)


class Migration(migrations.Migration):
    dependencies = [("locations", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

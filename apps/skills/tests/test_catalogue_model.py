import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.skills import services
from apps.skills.models import JobCategory, JobTitle, Skill, SkillAlias

pytestmark = pytest.mark.django_db


def test_names_become_searchable_terms():
    skill = Skill.objects.create(name_fa="فتوشاپ", name_en="Photoshop")
    terms = set(skill.aliases.values_list("normalized_text", flat=True))
    assert terms == {"فتوشاپ", "photoshop"}
    assert skill.aliases.filter(is_name=True).count() == 2


def test_renaming_updates_name_terms_and_keeps_manual_aliases():
    skill = services.create_entry(
        services.SKILL, name_fa="فتوشاپ", name_en="Photoshop", aliases=["PS"]
    )
    skill.name_en = "Adobe Photoshop"
    skill.save()
    terms = set(skill.aliases.values_list("normalized_text", flat=True))
    assert terms == {"فتوشاپ", "adobe photoshop", "ps"}


def test_entry_needs_at_least_one_name():
    with pytest.raises(IntegrityError), transaction.atomic():
        Skill.objects.create(name_fa="", name_en="")
    with pytest.raises(DjangoValidationError):
        Skill(name_fa="", name_en="").clean()


def test_same_term_cannot_belong_to_two_skills_at_db_level():
    a = Skill.objects.create(name_en="Photoshop")
    b = Skill.objects.create(name_en="Illustrator")
    with pytest.raises(IntegrityError), transaction.atomic():
        SkillAlias.objects.create(skill=b, text="PHOTOSHOP")
    assert a.aliases.count() == 1


def test_arabic_and_persian_letters_are_the_same_term():
    services.create_entry(services.SKILL, name_fa="کیبورد")
    with pytest.raises(ValidationError):
        services.create_entry(services.SKILL, name_fa="كيبورد")  # Arabic kaf/yeh


def test_zwnj_variant_is_a_duplicate():
    services.create_entry(services.JOB_TITLE, name_fa="توسعه‌دهنده وب")
    with pytest.raises(ValidationError):
        services.create_entry(services.JOB_TITLE, name_fa="توسعه دهنده وب")


def test_alias_cannot_steal_another_entries_name():
    a = services.create_entry(services.SKILL, name_en="Python")
    b = services.create_entry(services.SKILL, name_en="Django")
    with pytest.raises(ValidationError):
        services.add_alias(services.SKILL, b, "python")
    assert a.aliases.count() == 1


def test_model_clean_blocks_name_clash_for_admin_forms():
    services.create_entry(services.SKILL, name_en="Python")
    with pytest.raises(DjangoValidationError):
        Skill(name_en="python").clean()


def test_skills_and_titles_are_separate_catalogues():
    services.create_entry(services.SKILL, name_en="Design")
    services.create_entry(services.JOB_TITLE, name_en="Design")  # no clash across catalogues
    assert Skill.objects.count() == 1 and JobTitle.objects.count() == 1


def test_category_levels_and_seed():
    assert JobCategory.objects.filter(parent__isnull=True).count() >= 15  # seeded by migration
    top = JobCategory.objects.create(name_fa="الف", slug="x-top")
    sub = JobCategory.objects.create(name_fa="ب", slug="x-sub", parent=top)
    with pytest.raises(DjangoValidationError):
        JobCategory(name_fa="ج", slug="x-sub2", parent=sub).clean()
    with pytest.raises(DjangoValidationError):
        top.parent = sub
        top.clean()

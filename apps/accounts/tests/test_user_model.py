import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_user_model_is_custom():
    assert User._meta.label == "accounts.User"
    assert User.USERNAME_FIELD == "email"


def test_create_user_hashes_password_and_lowercases_email():
    user = User.objects.create_user("Amir@Example.COM", "S3cure-pass-123")
    assert user.email == "amir@example.com"
    assert user.password != "S3cure-pass-123"
    assert user.check_password("S3cure-pass-123")
    assert not user.is_staff and not user.is_superuser


def test_email_unique_case_insensitive():
    User.objects.create_user("a@example.com", "S3cure-pass-123")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("A@EXAMPLE.com", "S3cure-pass-123")


def test_db_rejects_non_lowercase_email_bypassing_save():
    User.objects.create_user("b@example.com", "S3cure-pass-123")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(email="b@example.com").update(email="B@example.com")


def test_email_required():
    with pytest.raises(ValueError):
        User.objects.create_user("", "S3cure-pass-123")


def test_create_superuser_flags():
    admin = User.objects.create_superuser("root@example.com", "S3cure-pass-123")
    assert admin.is_staff and admin.is_superuser


def test_superuser_requires_flags():
    with pytest.raises(ValueError):
        User.objects.create_superuser("x@example.com", "pw", is_staff=False)


def test_phone_validation_and_uniqueness():
    user = User(email="p@example.com", phone="12345")
    with pytest.raises(ValidationError):
        user.full_clean(exclude=["password"])
    User.objects.create_user("p1@example.com", "S3cure-pass-123", phone="09123456789")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("p2@example.com", "S3cure-pass-123", phone="09123456789")


def test_blank_phone_stored_as_null_so_many_users_without_phone():
    User.objects.create_user("n1@example.com", "S3cure-pass-123", phone="")
    User.objects.create_user("n2@example.com", "S3cure-pass-123", phone="")
    assert User.objects.filter(phone__isnull=True).count() == 2


def test_deactivated_user_cannot_authenticate():
    from django.contrib.auth import authenticate

    user = User.objects.create_user("d@example.com", "S3cure-pass-123")
    assert authenticate(email="d@example.com", password="S3cure-pass-123") == user
    user.is_active = False
    user.save()
    assert authenticate(email="d@example.com", password="S3cure-pass-123") is None

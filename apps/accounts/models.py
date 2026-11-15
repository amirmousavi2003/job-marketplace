from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

iran_mobile_validator = RegexValidator(
    regex=r"^09\d{9}$",
    message="Phone number must be an Iranian mobile number like 09123456789.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)  # hashes; None -> unusable password
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Single account type. Job-seeker / employer capability comes from profiles (Phase 3).
    Admin power comes only from Django's is_staff / permissions."""

    email = models.EmailField(unique=True)
    phone = models.CharField(
        max_length=11, unique=True, null=True, blank=True, validators=[iran_mobile_validator]
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email=Lower("email")), name="accounts_user_email_lowercase"
            ),
        ]

    def save(self, *args, **kwargs):
        # Emails are stored lowercase so uniqueness is effectively case-insensitive.
        self.email = (self.email or "").strip().lower()
        if self.phone == "":
            self.phone = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

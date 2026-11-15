from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

User = get_user_model()


def blacklist_all_tokens(user) -> None:
    """Invalidate every refresh token of a user (all devices)."""
    active = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=t) for t in active], ignore_conflicts=True
    )


def register_user(*, email: str, password: str, phone: str | None = None):
    return User.objects.create_user(email=email, password=password, phone=phone)


@transaction.atomic
def change_password(user, new_password: str) -> None:
    user.set_password(new_password)
    user.save(update_fields=["password"])
    blacklist_all_tokens(user)


@transaction.atomic
def deactivate_account(user) -> None:
    user.is_active = False
    user.save(update_fields=["is_active"])
    blacklist_all_tokens(user)


def make_reset_credentials(user) -> tuple[str, str]:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return uid, default_token_generator.make_token(user)


def get_user_for_reset(uid: str, token: str):
    """Return the user if uid+token are valid, else None. Tokens die after use or timeout."""
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return user if default_token_generator.check_token(user, token) else None

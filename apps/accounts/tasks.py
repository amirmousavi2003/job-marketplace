from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from .services import make_reset_credentials


@shared_task
def send_password_reset_email(user_id: int) -> None:
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return
    uid, token = make_reset_credentials(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    send_mail(
        subject="بازیابی رمز عبور",
        message=f"برای تعیین رمز عبور جدید روی لینک زیر بزنید:\n{link}\n\n"
        "اگر شما این درخواست را نداده‌اید، این ایمیل را نادیده بگیرید.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )

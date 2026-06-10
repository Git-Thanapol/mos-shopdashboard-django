import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    otp_enabled = models.BooleanField(
        "เปิดใช้รหัส OTP ทางอีเมล",
        default=True,
        help_text="เมื่อเปิดใช้ ผู้ใช้ต้องกรอกรหัสจากอีเมลตอนเข้าสู่ระบบ (จำอุปกรณ์ได้ 30 วัน)",
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "ผู้ใช้"
        verbose_name_plural = "ผู้ใช้"


class EmailOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, user):
        code = f"{secrets.randbelow(1_000_000):06d}"
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timezone.timedelta(seconds=settings.OTP_CODE_TTL_SECONDS),
        )

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_locked_out(self):
        if self.attempts < settings.OTP_MAX_ATTEMPTS or not self.last_attempt_at:
            return False
        lockout_until = self.last_attempt_at + timezone.timedelta(seconds=settings.OTP_LOCKOUT_SECONDS)
        return timezone.now() < lockout_until

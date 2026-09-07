from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import trusted_device
from .forms import OTPForm, ThaiLoginForm
from .models import EmailOTP

User = get_user_model()

OTP_SESSION_KEY = "otp_user_id"
OTP_BACKEND_KEY = "otp_backend"


def _send_otp(user):
    otp = EmailOTP.issue(user)
    send_mail(
        subject="รหัสยืนยันเข้าสู่ระบบ Shop Dashboard",
        message=(
            f"รหัสยืนยันของคุณคือ {otp.code}\n"
            f"รหัสมีอายุ 5 นาที หากคุณไม่ได้พยายามเข้าสู่ระบบ กรุณาเพิกเฉยต่ออีเมลนี้"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return otp


def login_view(request):
    if request.user.is_authenticated:
        return redirect("analytics:channel_select")

    form = ThaiLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if settings.OTP_LOGIN_ENABLED and user.otp_enabled and user.email and not trusted_device.is_trusted(request, user):
            request.session[OTP_SESSION_KEY] = user.pk
            request.session[OTP_BACKEND_KEY] = user.backend
            _send_otp(user)
            return redirect("accounts:otp")
        login(request, user)
        return redirect("analytics:channel_select")

    return render(request, "accounts/login.html", {"form": form})


def _otp_context(request):
    user_id = request.session.get(OTP_SESSION_KEY)
    if not user_id:
        return None, None
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        return None, None
    otp = user.otps.filter(used=False).order_by("-created_at").first()
    return user, otp


def otp_view(request):
    user, otp = _otp_context(request)
    if not user:
        return redirect("accounts:login")

    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if otp is None or otp.is_expired():
            messages.error(request, "รหัสหมดอายุแล้ว กรุณากดส่งรหัสอีกครั้ง")
        elif otp.is_locked_out():
            messages.error(request, "กรอกรหัสผิดเกิน 5 ครั้ง กรุณารอ 10 นาทีแล้วลองใหม่")
        elif form.cleaned_data["code"] != otp.code:
            otp.attempts += 1
            otp.last_attempt_at = timezone.now()
            otp.save(update_fields=["attempts", "last_attempt_at"])
            remaining = max(settings.OTP_MAX_ATTEMPTS - otp.attempts, 0)
            if remaining:
                messages.error(request, f"รหัสไม่ถูกต้อง (เหลือ {remaining} ครั้ง)")
            else:
                messages.error(request, "กรอกรหัสผิดเกิน 5 ครั้ง กรุณารอ 10 นาทีแล้วลองใหม่")
        else:
            otp.used = True
            otp.save(update_fields=["used"])
            backend = request.session.pop(OTP_BACKEND_KEY, None)
            del request.session[OTP_SESSION_KEY]
            login(request, user, backend=backend)
            response = redirect("analytics:channel_select")
            if form.cleaned_data["remember_device"]:
                trusted_device.mark_trusted(response, user)
            return response

    masked = user.email[:2] + "***" + user.email[user.email.find("@"):] if user.email else ""
    can_resend_at = None
    if otp:
        can_resend_at = otp.created_at + timezone.timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
    return render(
        request,
        "accounts/otp.html",
        {"form": form, "masked_email": masked, "can_resend_at": can_resend_at},
    )


@require_POST
def resend_otp(request):
    user, otp = _otp_context(request)
    if not user:
        return redirect("accounts:login")
    if otp and otp.is_locked_out():
        messages.error(request, "กรอกรหัสผิดเกิน 5 ครั้ง กรุณารอ 10 นาทีแล้วลองใหม่")
    elif otp and (timezone.now() - otp.created_at).total_seconds() < settings.OTP_RESEND_COOLDOWN_SECONDS:
        messages.warning(request, "กรุณารอ 60 วินาทีก่อนส่งรหัสใหม่")
    else:
        if otp:
            otp.used = True
            otp.save(update_fields=["used"])
        _send_otp(user)
        messages.success(request, "ส่งรหัสใหม่ไปที่อีเมลของคุณแล้ว")
    return redirect("accounts:otp")


def logout_view(request):
    logout(request)
    return redirect("accounts:login")

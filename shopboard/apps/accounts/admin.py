from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import EmailOTP, User


@admin.register(User)
class ShopUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("ความปลอดภัย", {"fields": ("otp_enabled",)}),)
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "otp_enabled")


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used", "attempts")
    readonly_fields = ("user", "code", "created_at", "expires_at", "used", "attempts", "last_attempt_at")

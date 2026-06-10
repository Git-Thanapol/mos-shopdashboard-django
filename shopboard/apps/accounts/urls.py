from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("otp/", views.otp_view, name="otp"),
    path("otp/resend/", views.resend_otp, name="otp_resend"),
    path("logout/", views.logout_view, name="logout"),
]

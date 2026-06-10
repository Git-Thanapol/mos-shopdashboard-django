from django import forms
from django.contrib.auth.forms import AuthenticationForm


class ThaiLoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
        "inactive": "บัญชีนี้ถูกระงับการใช้งาน",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "ชื่อผู้ใช้", "autofocus": True, "class": "input"}
        )
        self.fields["password"].widget.attrs.update(
            {"placeholder": "รหัสผ่าน", "class": "input"}
        )


class OTPForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{6}$",
        error_messages={"invalid": "กรุณากรอกรหัส 6 หลัก", "required": "กรุณากรอกรหัส 6 หลัก"},
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "6",
                "pattern": r"\d{6}",
                "class": "input otp-input",
                "autofocus": True,
            }
        ),
    )
    remember_device = forms.BooleanField(required=False, initial=True)

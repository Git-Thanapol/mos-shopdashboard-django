from django import forms

from .models import Employee, EmployeeAlias


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["name", "team", "salary_per_day", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-sm"}),
            "team": forms.TextInput(attrs={"class": "input input-sm"}),
            "salary_per_day": forms.NumberInput(attrs={"class": "input input-sm num-input", "step": "any"}),
        }


class EmployeeAliasForm(forms.ModelForm):
    class Meta:
        model = EmployeeAlias
        fields = ["employee", "raw_creator"]
        widgets = {
            "employee": forms.Select(attrs={"class": "input input-sm"}),
            "raw_creator": forms.TextInput(attrs={"class": "input input-sm", "list": "creator-options"}),
        }

    def clean_raw_creator(self):
        value = self.cleaned_data["raw_creator"].strip()
        if not value:
            raise forms.ValidationError("กรุณากรอกชื่อผู้สร้างออเดอร์")
        return value

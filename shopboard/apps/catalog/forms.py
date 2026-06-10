from django import forms

from .models import FixCost, MasterItem, Tag, TagGroup

NUM_ATTRS = {"class": "input input-sm num-input", "step": "any"}


class MasterItemForm(forms.ModelForm):
    class Meta:
        model = MasterItem
        exclude = ["channel", "updated_by"]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "input input-sm"}),
            "name": forms.TextInput(attrs={"class": "input input-sm"}),
            "type": forms.TextInput(attrs={"class": "input input-sm", "list": "type-options"}),
            **{
                f: forms.NumberInput(attrs=NUM_ATTRS)
                for f in [
                    "cost", "box_cost", "delivery_cost", "com_admin_pct", "com_tele_pct",
                    "p_jnt", "p_flash", "p_kerry", "p_thai_post", "p_dhl", "p_spx", "p_lex", "p_std",
                ]
            },
        }

    NUMERIC_FIELDS = [
        "cost", "box_cost", "delivery_cost", "com_admin_pct", "com_tele_pct",
        "p_jnt", "p_flash", "p_kerry", "p_thai_post", "p_dhl", "p_spx", "p_lex", "p_std",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.NUMERIC_FIELDS + ["name", "type"]:
            self.fields[f].required = False

    def clean_sku(self):
        from .importer import normalize_sku

        sku = normalize_sku(self.cleaned_data["sku"])
        if not sku:
            raise forms.ValidationError("กรุณากรอก SKU")
        return sku

    def clean(self):
        cleaned = super().clean()
        for f in self.NUMERIC_FIELDS:
            if cleaned.get(f) is None:
                cleaned[f] = 0
        if not cleaned.get("type"):
            cleaned["type"] = "กลุ่ม ปกติ"
        return cleaned


# distinct, dark-theme-friendly hues; new groups/tags draw a random one
TAG_PALETTE = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c", "#3498db",
    "#9b59b6", "#e84393", "#fd79a8", "#00cec9", "#6c5ce7", "#f39c12",
    "#27ae60", "#2980b9", "#8e44ad", "#d35400",
]


def random_tag_color() -> str:
    import secrets

    return secrets.choice(TAG_PALETTE)


class TagGroupForm(forms.ModelForm):
    class Meta:
        model = TagGroup
        # only the fields the tags page renders — sort_order/is_visible keep
        # their model defaults (a required-but-unrendered field made every
        # submit fail validation)
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-sm", "placeholder": "ชื่อกลุ่มแท็ก"}),
            "color": forms.TextInput(attrs={"type": "color", "class": "color-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("color", random_tag_color())


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-sm", "placeholder": "ชื่อแท็ก"}),
            "color": forms.TextInput(attrs={"type": "color", "class": "color-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("color", random_tag_color())


class FixCostForm(forms.ModelForm):
    class Meta:
        model = FixCost
        fields = ["year", "month", "label", "amount"]
        widgets = {
            "year": forms.NumberInput(attrs={"class": "input input-sm"}),
            "month": forms.NumberInput(attrs={"class": "input input-sm", "min": 1, "max": 12}),
            "label": forms.TextInput(attrs={"class": "input input-sm"}),
            "amount": forms.NumberInput(attrs=NUM_ATTRS),
        }

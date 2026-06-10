from django.conf import settings
from django.db import models

from apps.core.channels import Channel


class MasterItem(models.Model):
    """Product cost/commission config. Percent columns store numbers like 3 (= 3%);
    divide by 100 where used (plan §5.5/§5.7)."""

    channel = models.CharField(max_length=4, choices=Channel.choices, default=Channel.LIVE)
    sku = models.CharField("SKU", max_length=255, db_index=True)  # normalized: spaces stripped
    name = models.TextField("ชื่อสินค้า", blank=True, default="")
    type = models.CharField("หมวดหมู่", max_length=100, blank=True, default="กลุ่ม ปกติ")

    cost = models.DecimalField("ต้นทุน", max_digits=12, decimal_places=2, default=0)
    box_cost = models.DecimalField("ราคากล่อง", max_digits=12, decimal_places=2, default=0)
    delivery_cost = models.DecimalField("ค่าส่งเฉลี่ย", max_digits=12, decimal_places=2, default=0)

    com_admin_pct = models.DecimalField("คอม Admin (%)", max_digits=7, decimal_places=3, default=0)
    com_tele_pct = models.DecimalField("คอม Telesale (%)", max_digits=7, decimal_places=3, default=0)

    # courier COD % by normalized courier name (plan §5.4/§5.5)
    p_jnt = models.DecimalField("J&T (%)", max_digits=7, decimal_places=3, default=0)
    p_flash = models.DecimalField("Flash (%)", max_digits=7, decimal_places=3, default=0)
    p_kerry = models.DecimalField("Kerry (%)", max_digits=7, decimal_places=3, default=0)
    p_thai_post = models.DecimalField("ThailandPost (%)", max_digits=7, decimal_places=3, default=0)
    p_dhl = models.DecimalField("DHL (%)", max_digits=7, decimal_places=3, default=0)
    p_spx = models.DecimalField("SPX (%)", max_digits=7, decimal_places=3, default=0)
    p_lex = models.DecimalField("LEX (%)", max_digits=7, decimal_places=3, default=0)
    p_std = models.DecimalField("Standard (%)", max_digits=7, decimal_places=3, default=0)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel", "sku"], name="uniq_masteritem_channel_sku"),
        ]
        verbose_name = "สินค้า (Master)"
        verbose_name_plural = "สินค้า (Master)"

    def __str__(self):
        return f"[{self.channel}] {self.sku}"


class TagGroup(models.Model):
    name = models.TextField("ชื่อกลุ่ม", unique=True)
    color = models.CharField(max_length=20, default="#FF4B4B")
    sort_order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "กลุ่มแท็ก"
        verbose_name_plural = "กลุ่มแท็ก"

    def __str__(self):
        return self.name


class Tag(models.Model):
    group = models.ForeignKey(TagGroup, on_delete=models.CASCADE, related_name="tags")
    name = models.TextField("ชื่อแท็ก")
    color = models.CharField(max_length=20, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="uniq_tag_group_name"),
        ]
        verbose_name = "แท็ก"
        verbose_name_plural = "แท็ก"

    def __str__(self):
        return self.name


class ProductTag(models.Model):
    # sku is intentionally a plain string (no FK) so master re-imports never
    # cascade-delete tag assignments (plan §12)
    channel = models.CharField(max_length=4, choices=Channel.choices, default=Channel.LIVE)
    sku = models.CharField(max_length=255, db_index=True)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="product_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel", "sku", "tag"], name="uniq_producttag"),
        ]
        verbose_name = "แท็กสินค้า"
        verbose_name_plural = "แท็กสินค้า"

    def __str__(self):
        return f"[{self.channel}] {self.sku} → {self.tag}"


class FixCost(models.Model):
    """Fixed monthly costs for the P&L pages. LIVE channel only (plan §13)."""

    year = models.PositiveSmallIntegerField("ปี (ค.ศ.)")
    month = models.PositiveSmallIntegerField("เดือน")
    label = models.CharField("รายการ", max_length=255)
    amount = models.DecimalField("จำนวนเงิน", max_digits=14, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["year", "month", "label"], name="uniq_fixcost_period_label"),
        ]
        ordering = ["-year", "-month", "label"]
        verbose_name = "ค่าใช้จ่ายคงที่"
        verbose_name_plural = "ค่าใช้จ่ายคงที่"

    def __str__(self):
        return f"{self.year}-{self.month:02d} {self.label}"

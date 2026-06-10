from django.conf import settings
from django.db import models

from apps.core.channels import Channel


def upload_path(instance, filename):
    return f"uploads/{instance.shop.name}/{instance.kind.lower()}/{filename}"


class Shop(models.Model):
    name = models.CharField("ชื่อร้าน", max_length=255)
    channel = models.CharField(max_length=4, choices=Channel.choices, default=Channel.LIVE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel", "name"], name="uniq_shop_channel_name"),
        ]
        ordering = ["name"]
        verbose_name = "ร้านค้า"
        verbose_name_plural = "ร้านค้า"

    def __str__(self):
        return f"[{self.channel}] {self.name}"


class UploadedFile(models.Model):
    class Kind(models.TextChoices):
        SALES = "SALES", "ไฟล์ยอดขาย"
        ADS = "ADS", "ไฟล์โฆษณา"

    class Status(models.TextChoices):
        PENDING = "PENDING", "กำลังประมวลผล"
        PROCESSED = "PROCESSED", "นำเข้าแล้ว"
        ERROR = "ERROR", "ล้มเหลว"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    file = models.FileField(upload_to=upload_path)
    original_name = models.CharField(max_length=512)
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default="")
    row_count = models.IntegerField(default=0)
    date_min = models.DateField(null=True, blank=True)
    date_max = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # duplicate uploads (same content, same shop+kind) are rejected
            models.UniqueConstraint(fields=["shop", "kind", "sha256"], name="uniq_file_shop_kind_sha"),
        ]
        ordering = ["-uploaded_at"]
        verbose_name = "ไฟล์นำเข้า"
        verbose_name_plural = "ไฟล์นำเข้า"

    def __str__(self):
        return self.original_name


class SalesLine(models.Model):
    """One row per sales-file line. Raw values preserved; normalized/computed
    columns produced at ingest (plan §3.1, §5.1-5.6)."""

    file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE, related_name="sales_lines")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="sales_lines")
    channel = models.CharField(max_length=4, choices=Channel.choices, db_index=True)

    order_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=100, blank=True, default="")  # 'ยกเลิก' = cancelled
    courier_raw = models.CharField(max_length=255, blank=True, default="")
    courier_norm = models.CharField(max_length=255, blank=True, default="")
    order_time = models.DateTimeField(null=True, blank=True)
    date = models.DateField(null=True, blank=True, db_index=True)

    sku_raw = models.CharField(max_length=255, blank=True, default="")
    sku_norm = models.CharField(max_length=255, blank=True, default="", db_index=True)
    sku_root = models.CharField(max_length=255, blank=True, default="", db_index=True)

    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    creator = models.CharField(max_length=255, blank=True, default="")
    payment_method = models.CharField(max_length=255, blank=True, default="")
    work_type = models.CharField(max_length=255, blank=True, default="")
    product_name = models.TextField(blank=True, default="")

    role = models.CharField(max_length=10, default="Unknown")  # Admin / Telesale / Unknown
    is_cod = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "date"]),
            models.Index(fields=["channel", "sku_root"]),
        ]
        verbose_name = "รายการขาย"
        verbose_name_plural = "รายการขาย"


class AdSpend(models.Model):
    file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE, related_name="ad_rows")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="ad_rows")
    channel = models.CharField(max_length=4, choices=Channel.choices, db_index=True)

    date = models.DateField(db_index=True)
    campaign_name = models.TextField(blank=True, default="")
    # extracted from "[SKU]" in campaign name; NULL = no token (shown as 'ไม่ระบุ SKU')
    sku_root = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    cost = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "date"]),
        ]
        verbose_name = "ค่าโฆษณา"
        verbose_name_plural = "ค่าโฆษณา"

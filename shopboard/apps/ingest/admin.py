from django.contrib import admin

from .models import AdSpend, SalesLine, Shop, UploadedFile


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "is_active", "created_at")
    list_filter = ("channel",)


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "shop", "kind", "status", "row_count", "date_min", "date_max", "uploaded_at")
    list_filter = ("kind", "status", "shop__channel")
    search_fields = ("original_name",)


@admin.register(SalesLine)
class SalesLineAdmin(admin.ModelAdmin):
    list_display = ("order_id", "shop", "date", "sku_root", "quantity", "amount_paid", "role", "is_cod")
    list_filter = ("channel", "role", "is_cod")
    search_fields = ("order_id", "sku_root")


@admin.register(AdSpend)
class AdSpendAdmin(admin.ModelAdmin):
    list_display = ("date", "shop", "sku_root", "cost")
    list_filter = ("channel",)
    search_fields = ("sku_root", "campaign_name")

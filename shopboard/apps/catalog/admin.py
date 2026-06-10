from django.contrib import admin

from .models import FixCost, MasterItem, ProductTag, Tag, TagGroup


@admin.register(MasterItem)
class MasterItemAdmin(admin.ModelAdmin):
    list_display = ("sku", "channel", "name", "type", "cost", "box_cost", "delivery_cost", "updated_at")
    list_filter = ("channel", "type")
    search_fields = ("sku", "name")


class TagInline(admin.TabularInline):
    model = Tag
    extra = 0


@admin.register(TagGroup)
class TagGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "sort_order", "is_visible")
    inlines = [TagInline]


@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ("sku", "channel", "tag")
    list_filter = ("channel", "tag__group")
    search_fields = ("sku",)


@admin.register(FixCost)
class FixCostAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "label", "amount")
    list_filter = ("year",)

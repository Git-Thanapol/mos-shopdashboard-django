from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.home, name="home"),
    path("channel/", views.channel_select, name="channel_select"),
    path("channel/activate/", views.channel_activate, name="channel_activate"),
    path("reports/monthly/", views.report_monthly, name="report_monthly"),
    path("reports/daily/", views.report_daily, name="report_daily"),
    path("reports/ads/", views.report_ads, name="report_ads"),
    path("reports/products/graph/", views.product_graph, name="product_graph"),
    path("reports/commission/", views.commission, name="commission"),
    path("pnl/yearly/", views.pnl_yearly, name="pnl_yearly"),
    path("pnl/monthly/", views.pnl_monthly, name="pnl_monthly"),
    path("products/<str:sku>/", views.sku_detail, name="sku_detail"),
]

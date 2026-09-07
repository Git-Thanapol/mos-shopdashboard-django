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
    path("telesale/", views.telesale_dashboard, name="telesale"),
    path("telesale/employees/", views.employee_list, name="employee_list"),
    path("telesale/employees/create/", views.employee_create, name="employee_create"),
    path("telesale/employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("telesale/employees/<int:pk>/row/", views.employee_row, name="employee_row"),
    path("telesale/employees/<int:pk>/delete/", views.employee_delete, name="employee_delete"),
    path("telesale/aliases/create/", views.alias_create, name="alias_create"),
    path("telesale/aliases/<int:pk>/delete/", views.alias_delete, name="alias_delete"),
    path("pnl/yearly/", views.pnl_yearly, name="pnl_yearly"),
    path("pnl/monthly/", views.pnl_monthly, name="pnl_monthly"),
    path("products/<str:sku>/", views.sku_detail, name="sku_detail"),
]

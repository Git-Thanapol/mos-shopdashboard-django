from django.urls import path

from . import views

app_name = "ingest"

urlpatterns = [
    path("files/", views.file_manager, name="file_manager"),
    path("imports/", views.import_history, name="import_history"),
    path("shops/create/", views.shop_create, name="shop_create"),
    path("shops/<int:pk>/delete/", views.shop_delete, name="shop_delete"),
    path("shops/<int:shop_pk>/upload/<str:kind>/", views.upload, name="upload"),
    path("files/<int:pk>/delete/", views.file_delete, name="file_delete"),
    path("files/<int:pk>/detail/", views.file_detail, name="file_detail"),
]

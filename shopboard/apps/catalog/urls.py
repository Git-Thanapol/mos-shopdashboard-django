from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("master-items/", views.master_items, name="master_items"),
    path("master-items/rows/", views.master_rows, name="master_rows"),
    path("master-items/create/", views.master_create, name="master_create"),
    path("master-items/<int:pk>/edit/", views.master_edit, name="master_edit"),
    path("master-items/<int:pk>/row/", views.master_row, name="master_row"),
    path("master-items/<int:pk>/delete/", views.master_delete, name="master_delete"),
    path("master-items/import/", views.master_import_xlsx, name="master_import"),
    path("master-items/import-sheet/", views.master_import_sheet, name="master_import_sheet"),
    path("tags/", views.tags_page, name="tags"),
    path("tags/groups/create/", views.group_create, name="group_create"),
    path("tags/groups/<int:pk>/update/", views.group_update, name="group_update"),
    path("tags/groups/<int:pk>/delete/", views.group_delete, name="group_delete"),
    path("tags/groups/<int:group_pk>/tags/create/", views.tag_create, name="tag_create"),
    path("tags/<int:pk>/update/", views.tag_update, name="tag_update"),
    path("tags/<int:pk>/delete/", views.tag_delete, name="tag_delete"),
    path("tags/<int:pk>/toggle-sku/", views.tag_toggle_sku, name="tag_toggle_sku"),
]

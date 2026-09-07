from django.contrib import admin

from .models import Employee, EmployeeAlias


class EmployeeAliasInline(admin.TabularInline):
    model = EmployeeAlias
    extra = 1


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "salary_per_day", "is_active")
    list_filter = ("team", "is_active")
    list_editable = ("salary_per_day", "is_active")
    search_fields = ("name", "team")
    inlines = [EmployeeAliasInline]


@admin.register(EmployeeAlias)
class EmployeeAliasAdmin(admin.ModelAdmin):
    list_display = ("raw_creator", "employee")
    search_fields = ("raw_creator", "employee__name")
    autocomplete_fields = ("employee",)

from django.db import models


class Employee(models.Model):
    """A telesale/admin staff member. Channel-agnostic — the same person can
    work orders in both LIVE and TEST (plan §13 only separates shop/product data)."""

    name = models.CharField("ชื่อพนักงาน", max_length=255)
    team = models.CharField("ทีม", max_length=100, blank=True, default="")
    salary_per_day = models.DecimalField("เงินเดือน/วัน", max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "พนักงาน Telesale"
        verbose_name_plural = "พนักงาน Telesale"

    def __str__(self):
        return self.name

    @property
    def initials(self) -> str:
        parts = self.name.split()
        if len(parts) > 1:
            return (parts[0][:1] + parts[-1][:1]).upper()
        return self.name[:2].upper()


class EmployeeAlias(models.Model):
    """Maps SalesLine.creator raw text (unstructured, platform-specific) to an
    Employee. Orders whose creator has no alias show as 'ไม่ระบุพนักงาน'."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="aliases")
    raw_creator = models.CharField("ชื่อผู้สร้างออเดอร์ (ตามไฟล์)", max_length=255, unique=True)

    class Meta:
        ordering = ["raw_creator"]
        verbose_name = "ชื่อผู้สร้างออเดอร์ (Alias)"
        verbose_name_plural = "ชื่อผู้สร้างออเดอร์ (Alias)"

    def __str__(self):
        return f"{self.raw_creator} → {self.employee.name}"

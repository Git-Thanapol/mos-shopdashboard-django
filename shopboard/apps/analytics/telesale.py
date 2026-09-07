"""Per-employee performance aggregation for the TeleSale dashboard.

SalesLine has no employee FK — `creator` is free text from the shop platform
export. EmployeeAlias maps that raw text to a real Employee; unmapped orders
fall into a single "ไม่ระบุพนักงาน" bucket so nothing silently disappears.
Cost formulas replicate the fact-layer exactly (queries.employee_order_lines);
salary is time-based (per day in range), not order-based, so it's applied in
full regardless of the role filter.

The dashboard switches between all/Admin/Telesale instantly client-side (no
reload), so we compute all three variants here from one query pass.
"""
from . import queries
from .models import Employee, EmployeeAlias

UNMAPPED_KEY = "unmapped"
UNMAPPED_LABEL = "ไม่ระบุพนักงาน"
ROLES = ("all", "Admin", "Telesale")

ROW_FIELDS = (
    "orders", "revenue", "product_cost", "box_cost",
    "delivery_cost", "cod_cost", "commission", "salary", "profit",
)


def _empty_bucket():
    return {
        "orders": 0, "revenue": 0.0, "product_cost": 0.0,
        "box_cost": 0.0, "delivery_cost": 0.0, "cod_cost": 0.0,
        "commission": 0.0,
    }


def _build(order_rows, employees, alias_map, days, role):
    buckets: dict[int | str, dict] = {}
    for r in order_rows:
        if role != "all" and r["role"] != role:
            continue
        creator = (r["creator"] or "").strip()
        emp_id = alias_map.get(creator)
        key = emp_id if emp_id is not None else UNMAPPED_KEY
        b = buckets.setdefault(key, _empty_bucket())
        b["orders"] += 1
        b["revenue"] += float(r["revenue"] or 0)
        b["product_cost"] += float(r["product_cost"] or 0)
        b["box_cost"] += float(r["box_cost"] or 0)
        b["delivery_cost"] += float(r["delivery_cost"] or 0)
        b["cod_cost"] += float(r["cod_cost"] or 0)
        b["commission"] += float(r["com_admin"] or 0) + float(r["com_tele"] or 0)

    # keep every active employee visible even with zero matching orders
    for emp in employees.values():
        if emp.is_active:
            buckets.setdefault(emp.id, _empty_bucket())

    rows = []
    for key, b in buckets.items():
        emp = employees.get(key) if isinstance(key, int) else None
        name = emp.name if emp else UNMAPPED_LABEL
        team = emp.team if emp else ""
        salary = float(emp.salary_per_day) * days if emp else 0.0
        ops_cost = b["box_cost"] + b["delivery_cost"]
        profit = b["revenue"] - b["product_cost"] - ops_cost - b["cod_cost"] - b["commission"] - salary
        rows.append({
            "name": name, "team": team, "mapped": emp is not None,
            "orders": b["orders"], "revenue": b["revenue"],
            "product_cost": b["product_cost"], "box_cost": b["box_cost"],
            "delivery_cost": b["delivery_cost"], "cod_cost": b["cod_cost"],
            "commission": b["commission"], "salary": salary, "profit": profit,
            "margin": profit / b["revenue"] * 100 if b["revenue"] else 0.0,
        })

    rows.sort(key=lambda r: r["profit"], reverse=True)
    totals = {k: sum(r[k] for r in rows) for k in ROW_FIELDS}
    totals["margin"] = totals["profit"] / totals["revenue"] * 100 if totals["revenue"] else 0.0
    return rows, totals


def employee_performance_all_roles(channel, date_from, date_to):
    """Returns {"all": (rows, totals), "Admin": (...), "Telesale": (...)} —
    one query pass, three role-filtered aggregates."""
    days = (date_to - date_from).days + 1
    order_rows = queries.employee_order_lines(channel, date_from, date_to)
    alias_map = dict(EmployeeAlias.objects.values_list("raw_creator", "employee_id"))
    employees = {e.id: e for e in Employee.objects.all()}
    return {role: _build(order_rows, employees, alias_map, days, role) for role in ROLES}

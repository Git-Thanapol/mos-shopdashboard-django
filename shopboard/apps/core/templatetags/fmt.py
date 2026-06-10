"""Number formatting: 1,234,567 with '-' for zero/null (matches legacy fmt())."""
from django import template

register = template.Library()


@register.filter
def money(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{v:,.0f}" if v != 0 else "-"


@register.filter
def money2(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{v:,.2f}" if v != 0 else "-"


@register.filter
def pct(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{v:,.1f}%" if v != 0 else "-"


@register.filter
def neg(value):
    """CSS class hook for negative values."""
    try:
        return "neg" if float(value) < 0 else ""
    except (TypeError, ValueError):
        return ""

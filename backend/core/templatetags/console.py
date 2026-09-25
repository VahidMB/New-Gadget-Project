from decimal import Decimal, InvalidOperation
from django import template
register = template.Library()

@register.filter
def money(value):
    if value is None:
        return "—"
    try:
        number = Decimal(str(value))
        result = format(number, ",.8f").rstrip("0").rstrip(".")
        return result.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))
    except (InvalidOperation, ValueError):
        return value

@register.filter
def mb(value):
    return f"{value / 1048576:,.1f} MB" if isinstance(value, (int, float, Decimal)) else "—"

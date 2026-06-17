from decimal import Decimal

from django import template

from recipes.services import display_quantity


register = template.Library()


@register.filter
def get_item(mapping, key):
    return mapping.get(key)


@register.filter
def quantity(value):
    return display_quantity(value)


@register.filter
def unit_display(value, quantity=None):
    """Display a unit label; optionally convert large quantities to kg/L."""
    unit = str(value)
    if unit == "item":
        return ""

    if quantity is not None:
        try:
            qty = Decimal(str(quantity))
        except Exception:
            return unit

        if unit == "g" and qty >= 1000:
            return "kg"
        if unit == "ml" and qty >= 1000:
            return "L"

    return unit


@register.simple_tag
def plan_key(day, slot):
    return f"{day.isoformat()}_{slot}"


@register.simple_tag
def ingress_url(request, url):
    script_name = request.META.get("SCRIPT_NAME", "").rstrip("/")
    if script_name and url.startswith("/") and not url.startswith(f"{script_name}/"):
        return f"{script_name}{url}"
    return url


@register.filter
def smart_quantity_display(shopping_item):
    """Display quantity with smart unit conversion for kg/L."""
    try:
        qty = Decimal(str(shopping_item.quantity))
    except Exception:
        return f"{shopping_item.quantity} {shopping_item.unit}"

    unit = str(shopping_item.unit)

    if unit == "g" and qty >= 1000:
        converted = qty / 1000
        if converted == converted.to_integral():
            return f"{int(converted)} kg"
        return f"{converted.normalize()} kg"
    elif unit == "ml" and qty >= 1000:
        converted = qty / 1000
        if converted == converted.to_integral():
            return f"{int(converted)} L"
        return f"{converted.normalize()} L"
    else:
        qty_display = display_quantity(qty)
        unit_display_val = "" if unit == "item" else f" {unit}"
        return f"{qty_display}{unit_display_val}"


@register.filter
def shopping_item_display(item):
    """Smart display of a shopping list item quantity+unit."""
    return smart_quantity_display(item)


@register.simple_tag
def format_shopping_quantity(quantity, unit):
    """Format quantity+unit for shopping list with smart unit conversion."""
    qty = Decimal(str(quantity))
    if qty == 0:
        return ""
    if unit == "g" and qty >= 1000:
        return f"{display_quantity(qty / 1000)} kg"
    if unit == "ml" and qty >= 1000:
        return f"{display_quantity(qty / 1000)} L"
    if unit == "item":
        return display_quantity(qty)
    return f"{display_quantity(qty)} {unit}"

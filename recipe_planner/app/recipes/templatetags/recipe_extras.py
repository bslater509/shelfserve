from django import template

from recipes.services import display_quantity


register = template.Library()


@register.filter
def get_item(mapping, key):
    return mapping.get(key)


@register.filter
def quantity(value):
    return display_quantity(value)


@register.simple_tag
def plan_key(day, slot):
    return f"{day.isoformat()}_{slot}"


@register.simple_tag
def ingress_url(request, url):
    script_name = request.META.get("SCRIPT_NAME", "").rstrip("/")
    if script_name and url.startswith("/") and not url.startswith(f"{script_name}/"):
        return f"{script_name}{url}"
    return url

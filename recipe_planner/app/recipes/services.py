from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from .models import (
    ShoppingList,
    ShoppingListItem,
    SupermarketSection,
    UNIT_GROUPS,
    Unit,
)


def normalise_tag_name(name):
    return " ".join(name.strip().split()).lower()


def normalise_name(name):
    return " ".join(name.strip().split())


def display_quantity(value):
    value = Decimal(value)
    if value == value.to_integral():
        return str(value.quantize(Decimal("1")))
    return str(value.normalize())


def scale_quantity(quantity, planned_servings, recipe_servings):
    return (Decimal(quantity) * Decimal(planned_servings)) / Decimal(recipe_servings)


def unit_bucket(unit):
    group, multiplier, base_unit = UNIT_GROUPS[Unit(unit)]
    return group, multiplier, base_unit


def section_lookup(supermarket):
    sections = SupermarketSection.objects.filter(supermarket=supermarket)
    return {section.name.strip().lower(): section for section in sections}


def shopping_item_match_key(section_name, ingredient_name, unit):
    return (
        normalise_name(section_name).casefold(),
        normalise_name(ingredient_name).casefold(),
        unit,
    )


def planned_shopping_items(supermarket, plan_entries):
    sections = section_lookup(supermarket)
    grouped = defaultdict(lambda: {"quantity": Decimal("0"), "notes": set()})

    for entry in plan_entries.select_related("recipe").prefetch_related("recipe__ingredients__ingredient"):
        for recipe_ingredient in entry.recipe.ingredients.all():
            ingredient = recipe_ingredient.ingredient
            group, multiplier, base_unit = unit_bucket(recipe_ingredient.unit)
            scaled = scale_quantity(recipe_ingredient.quantity, entry.servings, entry.recipe.servings)
            section_key = (ingredient.category or "Uncategorised").strip()
            converted = scaled * multiplier
            key = (
                section_key.lower(),
                ingredient.name.lower(),
                group,
                base_unit,
            )
            grouped[key]["section_name"] = section_key
            grouped[key]["ingredient_name"] = ingredient.name
            grouped[key]["quantity"] += converted
            grouped[key]["unit"] = base_unit
            if recipe_ingredient.note:
                grouped[key]["notes"].add(recipe_ingredient.note)

    items = []
    for (section_key, _ingredient_key, _group, _base_unit), payload in grouped.items():
        section = sections.get(section_key)
        items.append(
            ShoppingListItem(
                section_name=payload["section_name"],
                section_order=section.order if section else 9999,
                ingredient_name=payload["ingredient_name"],
                quantity=payload["quantity"].quantize(Decimal("0.01")),
                unit=payload["unit"],
                notes=", ".join(sorted(payload["notes"])),
            )
        )

    return items


def build_shopping_list(supermarket, week_start, plan_entries):
    shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=week_start)
    items = planned_shopping_items(supermarket, plan_entries)
    for item in items:
        item.shopping_list = shopping_list

    ShoppingListItem.objects.bulk_create(items)
    return shopping_list


def regenerate_shopping_list(shopping_list, plan_entries):
    planned_items = planned_shopping_items(shopping_list.supermarket, plan_entries)

    with transaction.atomic():
        checked_items = {
            shopping_item_match_key(item.section_name, item.ingredient_name, item.unit): item.checked
            for item in ShoppingListItem.objects.select_for_update().filter(
                shopping_list=shopping_list,
                is_custom=False,
            )
        }
        ShoppingListItem.objects.filter(shopping_list=shopping_list, is_custom=False).delete()

        for item in planned_items:
            item.shopping_list = shopping_list
            key = shopping_item_match_key(item.section_name, item.ingredient_name, item.unit)
            item.checked = checked_items.get(key, False)

        ShoppingListItem.objects.bulk_create(planned_items)

    return shopping_list

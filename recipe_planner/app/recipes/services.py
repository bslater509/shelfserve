from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    Ingredient,
    PantryAdjustment,
    PantryItem,
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


def pantry_quantity_lookup():
    lookup = defaultdict(Decimal)
    for item in PantryItem.objects.select_related("ingredient"):
        group, multiplier, base_unit = unit_bucket(item.unit)
        key = (item.ingredient.name.casefold(), group, base_unit)
        lookup[key] += Decimal(item.quantity) * multiplier
    return lookup


def planned_shopping_items(supermarket, plan_entries, subtract_pantry=True):
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
    pantry_lookup = pantry_quantity_lookup() if subtract_pantry else {}
    for (section_key, _ingredient_key, _group, _base_unit), payload in grouped.items():
        pantry_key = (payload["ingredient_name"].casefold(), _group, _base_unit)
        pantry_available = pantry_lookup.get(pantry_key, Decimal("0"))
        pantry_used = min(payload["quantity"], pantry_available)
        if pantry_used:
            payload["quantity"] -= pantry_used
            pantry_lookup[pantry_key] -= pantry_used
            payload["notes"].add(f"pantry used: {display_quantity(pantry_used)} {_base_unit}")
        if payload["quantity"] <= 0:
            continue
        section = sections.get(section_key)
        pantry_used_quantity = pantry_used.quantize(Decimal("0.01")) if pantry_used else Decimal("0")
        items.append(
            ShoppingListItem(
                section_name=payload["section_name"],
                section_order=section.order if section else 9999,
                ingredient_name=payload["ingredient_name"],
                quantity=payload["quantity"].quantize(Decimal("0.01")),
                unit=payload["unit"],
                pantry_used_quantity=pantry_used_quantity,
                pantry_used_unit=_base_unit if pantry_used else "",
                notes=", ".join(sorted(payload["notes"])),
            )
        )

    return items


def mark_meal_cooked(entry):
    with transaction.atomic():
        entry = entry.__class__.objects.select_for_update().select_related("recipe").get(pk=entry.pk)
        if entry.pantry_consumed_at:
            return entry

        for recipe_ingredient in entry.recipe.ingredients.select_related("ingredient"):
            group, multiplier, _base_unit = unit_bucket(recipe_ingredient.unit)
            remaining_base = scale_quantity(recipe_ingredient.quantity, entry.servings, entry.recipe.servings) * multiplier
            pantry_items = PantryItem.objects.select_for_update().filter(
                ingredient=recipe_ingredient.ingredient,
                unit__in=[unit for unit, (unit_group, _multiplier, _base) in UNIT_GROUPS.items() if unit_group == group],
                quantity__gt=0,
            ).order_by("-quantity", "pk")

            for pantry_item in pantry_items:
                item_group, item_multiplier, _item_base_unit = unit_bucket(pantry_item.unit)
                if item_group != group or remaining_base <= 0:
                    continue
                available_base = Decimal(pantry_item.quantity) * item_multiplier
                used_base = min(remaining_base, available_base)
                used_item_quantity = (used_base / item_multiplier).quantize(Decimal("0.01"))
                pantry_item.quantity = ((available_base - used_base) / item_multiplier).quantize(Decimal("0.01"))
                pantry_item.save(update_fields=["quantity", "updated_at"])
                PantryAdjustment.objects.create(
                    meal_plan_entry=entry,
                    pantry_item=pantry_item,
                    ingredient=pantry_item.ingredient,
                    quantity=used_item_quantity,
                    unit=pantry_item.unit,
                )
                remaining_base -= used_base

        entry.pantry_consumed_at = timezone.now()
        entry.save(update_fields=["pantry_consumed_at"])
        entry.recipe.last_cooked_at = entry.pantry_consumed_at
        entry.recipe.save(update_fields=["last_cooked_at"])
        return entry


def undo_meal_cooked(entry):
    with transaction.atomic():
        entry = entry.__class__.objects.select_for_update().get(pk=entry.pk)
        if not entry.pantry_consumed_at:
            return entry

        for adjustment in entry.pantry_adjustments.select_related("pantry_item", "ingredient"):
            pantry_item = adjustment.pantry_item
            if pantry_item is None:
                pantry_item, _ = PantryItem.objects.get_or_create(
                    ingredient=adjustment.ingredient,
                    unit=adjustment.unit,
                    defaults={"quantity": Decimal("0")},
                )
            pantry_item.quantity = Decimal(pantry_item.quantity) + Decimal(adjustment.quantity)
            pantry_item.save(update_fields=["quantity", "updated_at"])

        entry.pantry_adjustments.all().delete()
        entry.pantry_consumed_at = None
        entry.save(update_fields=["pantry_consumed_at"])
        return entry


def build_shopping_list(supermarket, week_start, plan_entries):
    shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=week_start)
    items = planned_shopping_items(supermarket, plan_entries)
    for item in items:
        item.shopping_list = shopping_list

    ShoppingListItem.objects.bulk_create(items)
    return shopping_list


def restock_pantry_from_checked_items(shopping_list):
    restocked = 0
    with transaction.atomic():
        items = ShoppingListItem.objects.select_for_update().filter(
            shopping_list=shopping_list,
            checked=True,
        )
        for item in items:
            ingredient, _ = Ingredient.objects.get_or_create(name=normalise_name(item.ingredient_name))
            if ingredient.category != item.section_name and item.section_name:
                ingredient.category = item.section_name
                ingredient.save(update_fields=["category"])
            pantry_item, _ = PantryItem.objects.select_for_update().get_or_create(
                ingredient=ingredient,
                unit=item.unit,
                defaults={"quantity": Decimal("0")},
            )
            pantry_item.quantity = Decimal(pantry_item.quantity) + Decimal(item.quantity)
            pantry_item.save(update_fields=["quantity", "updated_at"])
            restocked += 1
    return restocked


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

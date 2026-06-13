from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import (
    Ingredient,
    MEAL_SLOTS,
    MealPlanEntry,
    MealPlanTemplate,
    MealPlanTemplateEntry,
    PantryItem,
    Recipe,
    RecipeIngredient,
    RecipeStep,
    SupermarketSection,
    Tag,
    Unit,
)
from .services import normalise_name, normalise_tag_name, undo_meal_cooked


def save_pantry_item_form(form, instance=None):
    ingredient_name = normalise_name(form.cleaned_data["ingredient_name"])
    ingredient, _ = Ingredient.objects.get_or_create(name=ingredient_name)
    quantity = form.cleaned_data["quantity"]
    unit = form.cleaned_data["unit"]
    low_stock_threshold = form.cleaned_data.get("low_stock_threshold")
    note = form.cleaned_data["note"].strip()
    duplicate = PantryItem.objects.filter(ingredient=ingredient, unit=unit).exclude(
        pk=instance.pk if instance else None
    ).first()
    if duplicate:
        duplicate.quantity = Decimal(duplicate.quantity) + Decimal(quantity)
        duplicate.low_stock_threshold = low_stock_threshold
        duplicate.note = note
        duplicate.save(update_fields=["quantity", "low_stock_threshold", "note", "updated_at"])
        if instance and instance.pk:
            instance.delete()
        return duplicate

    pantry_item = instance or PantryItem()
    pantry_item.ingredient = ingredient
    pantry_item.quantity = quantity
    pantry_item.unit = unit
    pantry_item.low_stock_threshold = low_stock_threshold
    pantry_item.note = note
    pantry_item.save()
    return pantry_item


def save_planner_entries(post_data, days, enabled_slots=None):
    if enabled_slots is None:
        enabled_slots = MEAL_SLOTS
    existing_entries = {
        (entry.date, entry.meal_slot): entry
        for entry in MealPlanEntry.objects.filter(date__range=(days[0], days[-1])).select_related("recipe")
    }
    submitted_entries = collect_planner_entries(post_data, days, enabled_slots=enabled_slots)
    with transaction.atomic():
        for day in days:
            for slot, _label in enabled_slots:
                existing = existing_entries.get((day, slot))
                submitted = submitted_entries.get((day, slot))

                if not submitted:
                    if existing:
                        undo_meal_cooked(existing)
                        existing.delete()
                    continue

                recipe = submitted["recipe"]
                servings = submitted["servings"]
                note = submitted["note"]
                if existing and existing.recipe_id == recipe.pk and existing.servings == servings and existing.note == note:
                    continue

                if existing:
                    undo_meal_cooked(existing)
                    existing.delete()
                MealPlanEntry.objects.create(date=day, meal_slot=slot, recipe=recipe, servings=servings, note=note)


def collect_planner_entries(post_data, days, enabled_slots=None):
    if enabled_slots is None:
        enabled_slots = MEAL_SLOTS
    entries = {}
    for day in days:
        for slot, _label in enabled_slots:
            recipe_id = post_data.get(f"recipe_{day.isoformat()}_{slot}")
            if not recipe_id:
                continue
            recipe = get_object_or_404(Recipe, pk=recipe_id)
            entries[(day, slot)] = {
                "recipe": recipe,
                "servings": parse_positive_int(post_data.get(f"servings_{day.isoformat()}_{slot}") or "1"),
                "note": normalise_name(post_data.get(f"note_{day.isoformat()}_{slot}", ""))[:160],
            }
    return entries


def save_meal_plan_template(name, post_data, days):
    submitted_entries = collect_planner_entries(post_data, days)
    existing_template = MealPlanTemplate.objects.filter(name__iexact=name).first()
    with transaction.atomic():
        template = existing_template or MealPlanTemplate(name=name)
        template.name = name
        template.save()
        template.entries.all().delete()
        template_entries = []
        for (day, slot), submitted in submitted_entries.items():
            template_entries.append(
                MealPlanTemplateEntry(
                    template=template,
                    day_offset=(day - days[0]).days,
                    meal_slot=slot,
                    recipe=submitted["recipe"],
                    servings=submitted["servings"],
                    note=submitted["note"],
                )
            )
        MealPlanTemplateEntry.objects.bulk_create(template_entries)
    return template


def entries_from_template(template, week_start):
    entries = {}
    for template_entry in template.entries.all():
        target_date = week_start + timedelta(days=template_entry.day_offset)
        copied_entry = MealPlanEntry(
            date=target_date,
            meal_slot=template_entry.meal_slot,
            recipe=template_entry.recipe,
            servings=template_entry.servings,
            note=template_entry.note,
        )
        entries[f"{target_date.isoformat()}_{template_entry.meal_slot}"] = copied_entry
    return entries


def parse_positive_int(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def save_supermarket_sections(supermarket, sections_data):
    names = parse_section_names(sections_data)
    saved_section_ids = []

    with transaction.atomic():
        existing_sections = {
            section.name.casefold(): section
            for section in SupermarketSection.objects.select_for_update().filter(supermarket=supermarket)
        }
        for index, name in enumerate(names):
            section = existing_sections.get(name.casefold())
            if section:
                if section.name != name or section.order != index:
                    section.name = name
                    section.order = index
                    section.save(update_fields=["name", "order"])
            else:
                section = SupermarketSection.objects.create(supermarket=supermarket, name=name, order=index)
            saved_section_ids.append(section.pk)

        stale_sections = SupermarketSection.objects.filter(supermarket=supermarket)
        if saved_section_ids:
            stale_sections = stale_sections.exclude(pk__in=saved_section_ids)
        stale_sections.delete()


def parse_section_names(sections_data):
    names = []
    seen = set()
    if isinstance(sections_data, str):
        lines = sections_data.splitlines()
    else:
        lines = sections_data
    for line in lines:
        name = normalise_name(line)
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def start_of_week(value, week_start):
    delta = (value.weekday() - week_start) % 7
    return value - timedelta(days=delta)


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def valid_imported_image_path(value):
    value = str(value or "").strip().replace("\\", "/")
    if not value.startswith("recipes/") or ".." in value.split("/"):
        return ""
    return value


def imported_image_media_url(path):
    if not path:
        return ""
    return default_storage.url(path)


def parse_ingredient_rows(post_data):
    rows = []
    names = post_data.getlist("ingredient_name")
    quantities = post_data.getlist("ingredient_quantity")
    units = post_data.getlist("ingredient_unit")
    notes = post_data.getlist("ingredient_note")
    categories = post_data.getlist("ingredient_category")

    for index, raw_name in enumerate(names):
        name = normalise_name(raw_name)
        if not name:
            continue
        try:
            quantity = Decimal(quantities[index])
        except (InvalidOperation, IndexError):
            continue
        if quantity <= 0:
            continue
        unit = units[index] if index < len(units) else Unit.ITEM
        if unit not in Unit.values:
            continue
        rows.append(
            {
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "note": notes[index].strip() if index < len(notes) else "",
                "category": normalise_name(categories[index]) if index < len(categories) else "",
                "order": index,
            }
        )
    return rows


def save_recipe_tags(recipe, tags_text):
    tags = []
    for raw_tag in tags_text.split(","):
        tag_name = normalise_tag_name(raw_tag)
        if tag_name:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)
    recipe.tags.set(tags)


def save_recipe_ingredients(recipe, rows):
    recipe.ingredients.all().delete()
    for row in rows:
        ingredient, _ = Ingredient.objects.get_or_create(name=row["name"])
        if row["category"] and ingredient.category != row["category"]:
            ingredient.category = row["category"]
            ingredient.save(update_fields=["category"])
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=row["quantity"],
            unit=row["unit"],
            note=row["note"],
            order=row["order"],
        )


def parse_step_rows(post_data):
    rows = []
    texts = post_data.getlist("step_text")
    durations = post_data.getlist("step_duration")

    for index, raw_text in enumerate(texts):
        text = raw_text.strip()
        if not text:
            continue

        duration_minutes = None
        if index < len(durations) and durations[index].strip():
            try:
                duration_minutes = int(durations[index])
                if duration_minutes <= 0:
                    duration_minutes = None
            except ValueError:
                duration_minutes = None

        rows.append(
            {
                "text": text,
                "duration_minutes": duration_minutes,
                "order": index,
            }
        )
    return rows


def save_recipe_steps(recipe, rows):
    recipe.steps.all().delete()
    for row in rows:
        RecipeStep.objects.create(
            recipe=recipe,
            text=row["text"],
            duration_minutes=row["duration_minutes"],
            order=row["order"],
        )

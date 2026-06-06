from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import models
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import PantryItemForm, RecipeForm, SettingsForm, SupermarketForm
from .models import (
    AppSetting,
    Ingredient,
    MEAL_SLOTS,
    MealPlanEntry,
    MealPlanTemplate,
    PantryItem,
    Recipe,
    ShoppingList,
    ShoppingListItem,
    Supermarket,
    SupermarketSection,
    Tag,
    Unit,
)
from .services import (
    build_shopping_list,
    mark_meal_cooked,
    normalise_name,
    normalise_tag_name,
    regenerate_shopping_list,
    restock_pantry_from_checked_items,
    undo_meal_cooked,
)
from .parser import parse_recipe_url, parse_recipe_text
from .view_helpers import (
    entries_from_template,
    imported_image_media_url,
    parse_date,
    parse_ingredient_rows,
    parse_step_rows,
    save_meal_plan_template,
    save_pantry_item_form,
    save_planner_entries,
    save_recipe_ingredients,
    save_recipe_steps,
    save_recipe_tags,
    save_supermarket_sections,
    start_of_week,
    valid_imported_image_path,
)


def dashboard(request):
    today = date.today()
    settings = AppSetting.current()
    week_start = start_of_week(today, settings.week_start)
    week_end = week_start + timedelta(days=6)
    active_lists = ShoppingList.objects.select_related("supermarket").annotate(
        total_items=Count("items"),
        checked_items=Count("items", filter=Q(items__checked=True)),
    )
    first_open_list = active_lists.filter(items__checked=False).distinct().first()
    context = {
        "recipe_count": Recipe.objects.count(),
        "supermarket_count": Supermarket.objects.count(),
        "planned_this_week_count": MealPlanEntry.objects.filter(date__range=(week_start, week_end)).count(),
        "open_list_count": ShoppingList.objects.filter(items__checked=False).distinct().count(),
        "low_stock_items": PantryItem.objects.select_related("ingredient").filter(
            low_stock_threshold__isnull=False,
            quantity__lte=models.F("low_stock_threshold"),
        )[:5],
        "today_entries": MealPlanEntry.objects.filter(date=today).select_related("recipe"),
        "upcoming_entries": MealPlanEntry.objects.filter(date__gt=today).select_related("recipe")[:5],
        "recent_lists": active_lists[:5],
        "first_open_list": first_open_list,
        "week_start": week_start,
        "week_end": week_end,
    }
    return render(request, "recipes/dashboard.html", context)

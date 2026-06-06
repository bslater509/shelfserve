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


def pantry_list(request):
    if request.method == "POST":
        form = PantryItemForm(request.POST)
        if form.is_valid():
            pantry_item = save_pantry_item_form(form)
            messages.success(request, f"Saved {pantry_item.ingredient.name} in pantry.")
            return redirect("pantry_list")
    else:
        form = PantryItemForm()

    return render(
        request,
        "recipes/pantry_list.html",
        {
            "form": form,
            "pantry_items": PantryItem.objects.select_related("ingredient"),
            "suggested_ingredients": Ingredient.objects.values_list("name", flat=True).distinct().order_by("name"),
        },
    )

@require_POST
def edit_pantry_item(request, pk):
    pantry_item = get_object_or_404(PantryItem.objects.select_related("ingredient"), pk=pk)
    form = PantryItemForm(request.POST, instance=pantry_item)
    if form.is_valid():
        saved_item = save_pantry_item_form(form, pantry_item)
        messages.success(request, f"Updated {saved_item.ingredient.name} in pantry.")
    else:
        messages.error(request, "Pantry item could not be updated.")
    return redirect("pantry_list")

@require_POST
def delete_pantry_item(request, pk):
    pantry_item = get_object_or_404(PantryItem.objects.select_related("ingredient"), pk=pk)
    ingredient_name = pantry_item.ingredient.name
    pantry_item.delete()
    messages.success(request, f"Removed {ingredient_name} from pantry.")
    return redirect("pantry_list")

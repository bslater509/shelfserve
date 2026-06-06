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


def supermarket_list(request):
    if request.method == "POST":
        form = SupermarketForm(request.POST)
        if form.is_valid():
            supermarket = form.save()
            messages.success(request, "Supermarket saved.")
            return redirect("supermarket_detail", pk=supermarket.pk)
    else:
        form = SupermarketForm()
    return render(
        request,
        "recipes/supermarket_list.html",
        {"form": form, "supermarkets": Supermarket.objects.prefetch_related("sections")},
    )

def supermarket_detail(request, pk):
    supermarket = get_object_or_404(Supermarket.objects.prefetch_related("sections"), pk=pk)
    if request.method == "POST":
        form = SupermarketForm(request.POST, instance=supermarket)
        sections_list = request.POST.getlist("sections")
        if form.is_valid():
            supermarket = form.save()
            save_supermarket_sections(supermarket, sections_list)
            messages.success(request, "Supermarket updated.")
            return redirect("supermarket_detail", pk=supermarket.pk)
    else:
        form = SupermarketForm(instance=supermarket)

    sections = list(supermarket.sections.all())
    default_aisles = ["Fruit & veg", "Bakery", "Dairy", "Meat & Poultry", "Frozen", "Pantry", "Drinks"]
    return render(
        request,
        "recipes/supermarket_detail.html",
        {
            "supermarket": supermarket,
            "form": form,
            "sections": sections,
            "default_aisles": default_aisles,
        },
    )

def settings_view(request):
    settings = AppSetting.current()
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = SettingsForm(instance=settings)
    return render(request, "recipes/settings.html", {"form": form})

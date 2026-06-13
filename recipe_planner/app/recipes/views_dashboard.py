from datetime import date, timedelta

from django.db import models
from django.db.models import Count, Q
from django.shortcuts import render

from .models import AppSetting, MealPlanEntry, PantryItem, Recipe, ShoppingList, Supermarket
from .view_helpers import start_of_week


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

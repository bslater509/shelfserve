from datetime import date, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import AppSetting, MEAL_SLOTS, MealPlanEntry, MealPlanTemplate, Recipe, ShoppingList, Supermarket
from .services import mark_meal_cooked, normalise_name, undo_meal_cooked
from .view_helpers import (
    entries_from_template,
    parse_date,
    save_meal_plan_template,
    save_planner_entries,
    start_of_week,
)


def planner(request):
    settings = AppSetting.current()
    selected = parse_date(request.GET.get("week")) or date.today()
    week_start = start_of_week(selected, settings.week_start)
    days = [week_start + timedelta(days=offset) for offset in range(7)]
    recipes = Recipe.objects.prefetch_related("tags")
    copy_from_str = request.GET.get("copy_from")
    copy_from_date = parse_date(copy_from_str)
    template_id = request.GET.get("template")
    selected_template = None
    template_preview = False

    if request.method == "POST":
        if request.POST.get("planner_action") == "save_template":
            template_name = normalise_name(request.POST.get("template_name", ""))[:120]
            if not template_name:
                messages.error(request, "Template name is required.")
                return redirect(f"{reverse('planner')}?week={week_start.isoformat()}")
            saved_template = save_meal_plan_template(template_name, request.POST, days)
            messages.success(request, f"Saved {saved_template.name} as a reusable planner template.")
        else:
            save_planner_entries(request.POST, days)
            messages.success(request, "Meal plan saved.")
        return redirect(f"{reverse('planner')}?week={week_start.isoformat()}")

    if template_id:
        selected_template = get_object_or_404(
            MealPlanTemplate.objects.prefetch_related("entries__recipe"),
            pk=template_id,
        )
        entries = entries_from_template(selected_template, week_start)
        template_preview = True
        messages.info(request, f"Previewing template {selected_template.name}. Click 'Save meal plan' to apply it.")
    elif copy_from_date:
        copy_from_start = start_of_week(copy_from_date, settings.week_start)
        entries = {}
        for entry in MealPlanEntry.objects.filter(
            date__range=(copy_from_start, copy_from_start + timedelta(days=6))
        ).select_related("recipe"):
            offset_days = (entry.date - copy_from_start).days
            target_date = week_start + timedelta(days=offset_days)
            copied_entry = MealPlanEntry(
                date=target_date,
                meal_slot=entry.meal_slot,
                recipe=entry.recipe,
                servings=entry.servings,
                note=entry.note,
            )
            entries[f"{target_date.isoformat()}_{entry.meal_slot}"] = copied_entry
        messages.info(request, f"Previewing meals copied from week of {copy_from_start.strftime('%d %b %Y')}. Click 'Save planner' to keep them.")
    else:
        entries = {
            f"{entry.date.isoformat()}_{entry.meal_slot}": entry
            for entry in MealPlanEntry.objects.filter(date__range=(days[0], days[-1])).select_related("recipe")
        }

    supermarkets = Supermarket.objects.all()
    latest_lists_by_supermarket = {}
    for shopping_list in ShoppingList.objects.filter(week_start=week_start).select_related("supermarket").order_by("-created_at"):
        latest_lists_by_supermarket.setdefault(shopping_list.supermarket_id, shopping_list)

    return render(
        request,
        "recipes/planner.html",
        {
            "days": days,
            "meal_slots": MEAL_SLOTS,
            "recipes": recipes,
            "entries": entries,
            "supermarkets": supermarkets,
            "latest_lists_by_supermarket": latest_lists_by_supermarket,
            "templates": MealPlanTemplate.objects.prefetch_related("entries").all(),
            "selected_template": selected_template,
            "template_preview": template_preview,
            "week_start": week_start,
            "previous_week": week_start - timedelta(days=7),
            "next_week": week_start + timedelta(days=7),
            "today_week": start_of_week(date.today(), settings.week_start),
        },
    )

@require_POST
def delete_meal_plan_template(request, pk):
    template = get_object_or_404(MealPlanTemplate, pk=pk)
    template_name = template.name
    template.delete()
    messages.success(request, f"Deleted planner template {template_name}.")
    return redirect(request.META.get("HTTP_REFERER", reverse("planner")))

@require_POST
def cook_planner_entry(request, pk):
    entry = get_object_or_404(MealPlanEntry.objects.select_related("recipe"), pk=pk)
    mark_meal_cooked(entry)
    messages.success(request, f"Marked {entry.recipe.title} as cooked and updated pantry stock.")
    return redirect(f"{reverse('planner')}?week={entry.date.isoformat()}")

@require_POST
def undo_cook_planner_entry(request, pk):
    entry = get_object_or_404(MealPlanEntry.objects.select_related("recipe"), pk=pk)
    undo_meal_cooked(entry)
    messages.success(request, f"Restored pantry stock for {entry.recipe.title}.")
    return redirect(f"{reverse('planner')}?week={entry.date.isoformat()}")

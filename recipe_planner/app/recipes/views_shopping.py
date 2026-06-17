from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Ingredient, MealPlanEntry, ShoppingList, ShoppingListItem, Supermarket, SupermarketSection, Unit
from .services import build_shopping_list, normalise_name, regenerate_shopping_list, restock_pantry_from_checked_items
from .view_helpers import parse_date


@require_POST
def generate_shopping_list(request):
    supermarket = get_object_or_404(Supermarket, pk=request.POST.get("supermarket"))
    week_start = parse_date(request.POST.get("week_start"))
    if not week_start:
        return HttpResponseBadRequest("Invalid week start.")
    plan_entries = MealPlanEntry.objects.filter(
        date__range=(week_start, week_start + timedelta(days=6))
    )
    if not plan_entries.exists():
        messages.error(request, "Plan at least one recipe before generating a shopping list.")
        return redirect(f"{reverse('planner')}?week={week_start.isoformat()}")
    shopping_list = ShoppingList.objects.filter(
        supermarket=supermarket,
        week_start=week_start,
    ).order_by("-created_at").first()
    if shopping_list:
        regenerate_shopping_list(shopping_list, plan_entries)
        messages.success(request, "Latest shopping list refreshed.")
    else:
        shopping_list = build_shopping_list(supermarket, week_start, plan_entries)
        messages.success(request, "Shopping list generated.")
    return redirect("shopping_list_detail", pk=shopping_list.pk)

def shopping_list_detail(request, pk):
    shopping_list = get_object_or_404(
        ShoppingList.objects.select_related("supermarket").prefetch_related("items"),
        pk=pk,
    )
    total_items = shopping_list.items.count()
    checked_items = shopping_list.items.filter(checked=True).count()
    grouped_items = []
    current_section = None
    for item in shopping_list.items.all():
        if not grouped_items or item.section_name != current_section:
            current_section = item.section_name
            grouped_items.append((current_section, []))
        grouped_items[-1][1].append(item)

    suggested_ingredients = list(Ingredient.objects.values_list("name", flat=True).distinct().order_by("name"))
    # Suggest supermarket-specific sections if any exist
    supermarket_sections = list(shopping_list.supermarket.sections.values_list("name", flat=True).order_by("order", "name"))
    # Merge with general ingredient categories
    ingredient_categories = list(Ingredient.objects.exclude(category__isnull=True).values_list("category__name", flat=True).distinct())
    suggested_categories = sorted(list(set(supermarket_sections + ingredient_categories)))

    return render(
        request,
        "recipes/shopping_list_detail.html",
        {
            "shopping_list": shopping_list,
            "grouped_items": grouped_items,
            "total_items": total_items,
            "checked_items": checked_items,
            "units": Unit.choices,
            "suggested_ingredients": suggested_ingredients,
            "suggested_categories": suggested_categories,
        },
    )

@require_POST
def toggle_shopping_item(request, pk):
    item = get_object_or_404(ShoppingListItem, pk=pk)
    item.checked = not item.checked
    item.save(update_fields=["checked"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"id": item.pk, "checked": item.checked})
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", reverse("shopping_list_detail", args=[item.shopping_list_id])))

@require_POST
def regenerate_existing_shopping_list(request, pk):
    shopping_list = get_object_or_404(ShoppingList.objects.select_related("supermarket"), pk=pk)
    plan_entries = MealPlanEntry.objects.filter(
        date__range=(shopping_list.week_start, shopping_list.week_start + timedelta(days=6))
    )
    if not plan_entries.exists():
        messages.error(request, "Plan at least one recipe before regenerating this shopping list.")
        return redirect("shopping_list_detail", pk=pk)

    regenerate_shopping_list(shopping_list, plan_entries)
    messages.success(request, "Shopping list regenerated.")
    return redirect("shopping_list_detail", pk=pk)

@require_POST
def restock_shopping_list(request, pk):
    shopping_list = get_object_or_404(ShoppingList, pk=pk)
    restocked = restock_pantry_from_checked_items(shopping_list)
    if restocked:
        messages.success(request, f"Restocked pantry from {restocked} checked shopping item(s).")
    else:
        messages.error(request, "Check at least one shopping item before restocking pantry.")
    return redirect("shopping_list_detail", pk=pk)

@require_POST
def add_shopping_item(request, pk):
    shopping_list = get_object_or_404(ShoppingList, pk=pk)
    ingredient_name = normalise_name(request.POST.get("ingredient_name", ""))
    if not ingredient_name:
        messages.error(request, "Ingredient name is required.")
        return redirect("shopping_list_detail", pk=pk)

    quantity_str = request.POST.get("quantity", "1")
    try:
        quantity = Decimal(quantity_str)
    except (InvalidOperation, ValueError):
        quantity = Decimal("1")
    if quantity <= 0:
        quantity = Decimal("1")

    unit = request.POST.get("unit", Unit.ITEM)
    if unit not in Unit.values:
        unit = Unit.ITEM

    section_name = normalise_name(request.POST.get("section_name", "Uncategorised")) or "Uncategorised"

    # Find section order
    supermarket = shopping_list.supermarket
    section = SupermarketSection.objects.filter(
        supermarket=supermarket,
        name__iexact=section_name
    ).first()

    section_order = section.order if section else 9999

    ShoppingListItem.objects.create(
        shopping_list=shopping_list,
        ingredient_name=ingredient_name,
        quantity=quantity,
        unit=unit,
        section_name=section_name,
        section_order=section_order,
        notes=request.POST.get("notes", "").strip(),
        is_custom=True,
    )
    messages.success(request, f"Added {ingredient_name} to shopping list.")
    return redirect("shopping_list_detail", pk=pk)

@require_POST
def edit_shopping_item(request, pk):
    item = get_object_or_404(ShoppingListItem.objects.select_related("shopping_list__supermarket"), pk=pk)
    ingredient_name = normalise_name(request.POST.get("ingredient_name", ""))
    if not ingredient_name:
        messages.error(request, "Ingredient name is required.")
        return redirect("shopping_list_detail", pk=item.shopping_list_id)

    try:
        quantity = Decimal(request.POST.get("quantity", "1"))
    except (InvalidOperation, ValueError):
        messages.error(request, "Quantity must be a valid number.")
        return redirect("shopping_list_detail", pk=item.shopping_list_id)
    if quantity <= 0:
        messages.error(request, "Quantity must be greater than zero.")
        return redirect("shopping_list_detail", pk=item.shopping_list_id)

    unit = request.POST.get("unit", Unit.ITEM)
    if unit not in Unit.values:
        unit = Unit.ITEM

    section_name = normalise_name(request.POST.get("section_name", "Uncategorised")) or "Uncategorised"
    section = SupermarketSection.objects.filter(
        supermarket=item.shopping_list.supermarket,
        name__iexact=section_name,
    ).first()

    item.ingredient_name = ingredient_name
    item.quantity = quantity
    item.unit = unit
    item.section_name = section_name
    item.section_order = section.order if section else 9999
    item.notes = request.POST.get("notes", "").strip()
    item.save(update_fields=["ingredient_name", "quantity", "unit", "section_name", "section_order", "notes"])
    messages.success(request, "Shopping item updated.")
    return redirect("shopping_list_detail", pk=item.shopping_list_id)

@require_POST
def delete_shopping_item(request, pk):
    item = get_object_or_404(ShoppingListItem, pk=pk)
    shopping_list_id = item.shopping_list_id
    item.delete()
    messages.success(request, "Shopping item deleted.")
    return redirect("shopping_list_detail", pk=shopping_list_id)

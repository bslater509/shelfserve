"""Category management views: CRUD for IngredientCategory."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Ingredient, IngredientCategory


def category_list(request):
    """List all categories with ingredient counts."""
    categories = IngredientCategory.objects.annotate(
        ingredient_count=Count("ingredient")
    ).order_by("order", "name")
    return render(request, "recipes/category_list.html", {
        "categories": categories,
    })


@require_POST
def category_create(request):
    """Create a new ingredient category."""
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Category name is required.")
        return redirect("category_list")
    _, created = IngredientCategory.objects.get_or_create(name=name)
    if created:
        messages.success(request, f"Category '{name}' created.")
    else:
        messages.info(request, f"Category '{name}' already exists.")
    return redirect("category_list")


@require_POST
def category_rename(request, pk):
    """Inline rename a category."""
    category = get_object_or_404(IngredientCategory, pk=pk)
    new_name = request.POST.get("name", "").strip()
    if not new_name:
        messages.error(request, "Category name is required.")
        return redirect("category_list")
    if IngredientCategory.objects.filter(name=new_name).exclude(pk=pk).exists():
        messages.error(request, f"A category named '{new_name}' already exists.")
        return redirect("category_list")
    category.name = new_name
    category.save(update_fields=["name"])
    messages.success(request, f"Category renamed to '{new_name}'.")
    return redirect("category_list")


@require_POST
def category_move_up(request, pk):
    """Move a category up by swapping its order with the previous one."""
    category = get_object_or_404(IngredientCategory, pk=pk)
    prev_category = IngredientCategory.objects.filter(
        order__lt=category.order
    ).order_by("-order").first()
    if prev_category is None:
        messages.info(request, "Category is already at the top.")
        return redirect("category_list")
    with transaction.atomic():
        prev_order = prev_category.order
        prev_category.order = category.order
        category.order = prev_order
        prev_category.save(update_fields=["order"])
        category.save(update_fields=["order"])
    messages.success(request, f"Moved '{category.name}' up.")
    return redirect("category_list")


@require_POST
def category_move_down(request, pk):
    """Move a category down by swapping its order with the next one."""
    category = get_object_or_404(IngredientCategory, pk=pk)
    next_category = IngredientCategory.objects.filter(
        order__gt=category.order
    ).order_by("order").first()
    if next_category is None:
        messages.info(request, "Category is already at the bottom.")
        return redirect("category_list")
    with transaction.atomic():
        next_order = next_category.order
        next_category.order = category.order
        category.order = next_order
        next_category.save(update_fields=["order"])
        category.save(update_fields=["order"])
    messages.success(request, f"Moved '{category.name}' down.")
    return redirect("category_list")


@require_POST
def category_delete(request, pk):
    """Delete a category. Blocks if ingredients are assigned to it."""
    category = get_object_or_404(IngredientCategory, pk=pk)
    assigned = Ingredient.objects.filter(category=category).count()
    if assigned:
        messages.error(
            request,
            f"Cannot delete '{category.name}' — it is assigned to "
            f"{assigned} ingredient(s). Reassign them first.",
        )
        return redirect("category_list")
    name = category.name
    category.delete()
    messages.success(request, f"Category '{name}' deleted.")
    return redirect("category_list")

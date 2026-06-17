"""Ingredient management views: list, filter, and bulk-edit ingredients."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Ingredient, IngredientCategory


def ingredient_list(request):
    """List all ingredients with filter/search and category assignment."""
    category_filter = request.GET.get("category", "")
    search = request.GET.get("search", "").strip()
    show_uncategorised = request.GET.get("uncategorised", "") == "1"

    ingredients = (
        Ingredient.objects.select_related("category", "canonical")
        .order_by("name")
    )

    if search:
        ingredients = ingredients.filter(name__icontains=search)
    if category_filter:
        ingredients = ingredients.filter(category__name=category_filter)
    elif show_uncategorised:
        ingredients = ingredients.filter(category__isnull=True)

    categories = IngredientCategory.objects.annotate(
        ingredient_count=Count("ingredient")
    ).order_by("order", "name")

    # Counts for the header
    total_uncategorised = Ingredient.objects.filter(category__isnull=True).count()
    total_canonical = Ingredient.objects.exclude(canonical__isnull=True).count()

    # ---- pagination ------------------------------------------------------
    total_count = ingredients.count()
    paginator = Paginator(ingredients, 50)
    page_num = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_num)

    return render(request, "recipes/ingredient_list.html", {
        "ingredients": page_obj,
        "categories": categories,
        "category_filter": category_filter,
        "search": search,
        "show_uncategorised": show_uncategorised,
        "total_uncategorised": total_uncategorised,
        "total_canonical": total_canonical,
        "total_count": Ingredient.objects.count(),
    })


@require_POST
def ingredient_bulk_edit(request):
    """Handle bulk ingredient updates via POST and redirect to list."""
    action = request.POST.get("action", "")
    selected_ids = request.POST.getlist("selected_ids", [])

    if action == "set_category" and selected_ids:
        new_category_id = request.POST.get("new_category", "")
        if new_category_id:
            Ingredient.objects.filter(pk__in=selected_ids).update(
                category_id=new_category_id
            )
            messages.success(
                request,
                f"Updated category for {len(selected_ids)} ingredient(s).",
            )
    elif action == "clear_canonical" and selected_ids:
        Ingredient.objects.filter(pk__in=selected_ids).update(canonical=None)
        messages.success(
            request,
            f"Cleared canonical for {len(selected_ids)} ingredient(s).",
        )

    return redirect("ingredient_list")


def ingredient_edit(request, pk):
    """Edit a single ingredient: name, category, and canonical."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    categories = IngredientCategory.objects.all()
    all_ingredients = Ingredient.objects.exclude(pk=pk).order_by("name")

    if request.method == "POST":
        ingredient.name = request.POST.get("name", ingredient.name).strip()
        cat_id = request.POST.get("category")
        if cat_id:
            ingredient.category = get_object_or_404(IngredientCategory, pk=cat_id)
        else:
            ingredient.category = None
        canonical_id = request.POST.get("canonical")
        if canonical_id:
            ingredient.canonical = get_object_or_404(Ingredient, pk=canonical_id)
        else:
            ingredient.canonical = None
        ingredient.save()
        messages.success(request, f"Updated {ingredient.name}.")
        return redirect("ingredient_list")

    return render(
        request,
        "recipes/ingredient_edit.html",
        {
            "ingredient": ingredient,
            "categories": categories,
            "all_ingredients": all_ingredients,
        },
    )


@require_POST
def ingredient_set_category(request, pk):
    """Set category for a single ingredient."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    category_name = request.POST.get("category", "").strip()
    if category_name:
        category, _ = IngredientCategory.objects.get_or_create(name=category_name)
        ingredient.category = category
    else:
        ingredient.category = None
    ingredient.save(update_fields=["category"])
    messages.success(request, f"Category for '{ingredient.name}' updated.")
    return redirect("ingredient_list")


@require_POST
def ingredient_set_canonical(request, pk):
    """Set canonical for a single ingredient."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    canonical_name = request.POST.get("canonical", "").strip()
    if canonical_name:
        canonical, _ = Ingredient.objects.get_or_create(
            name=canonical_name,
            defaults={"name": canonical_name}
        )
        ingredient.canonical = canonical
    else:
        ingredient.canonical = None
    ingredient.save(update_fields=["canonical"])
    messages.success(request, f"Canonical for '{ingredient.name}' updated.")
    return redirect("ingredient_list")


@require_POST
def ingredient_bulk_categorise(request):
    """Bulk set category for selected ingredients."""
    pks = request.POST.getlist("ingredient_ids")
    category_name = request.POST.get("category", "").strip()
    if not pks:
        messages.error(request, "No ingredients selected.")
        return redirect("ingredient_list")
    count = 0
    if category_name:
        category, _ = IngredientCategory.objects.get_or_create(name=category_name)
        count = Ingredient.objects.filter(pk__in=pks).update(category=category)
    else:
        count = Ingredient.objects.filter(pk__in=pks).update(category=None)
    messages.success(request, f"Updated category for {count} ingredient(s).")
    return redirect("ingredient_list")


@require_POST
def ingredient_bulk_merge(request):
    """Merge selected ingredients into a canonical ingredient."""
    selected_ids = request.POST.getlist("ingredient_ids")
    canonical_id = request.POST.get("canonical")

    if len(selected_ids) < 2:
        messages.error(request, "Select at least two ingredients to merge.")
        return redirect("ingredient_list")

    canonical = get_object_or_404(Ingredient, pk=canonical_id)
    to_merge = [pk for pk in selected_ids if str(pk) != str(canonical_id)]

    if not to_merge:
        messages.error(request, "Select at least one other ingredient to merge into the canonical.")
        return redirect("ingredient_list")

    merged = 0
    with transaction.atomic():
        for pk in to_merge:
            ingredient = Ingredient.objects.get(pk=pk)
            ingredient.recipeingredient_set.update(ingredient=canonical)
            ingredient.pantryitem_set.update(ingredient=canonical)
            ingredient.pantryadjustment_set.update(ingredient=canonical)
            if not canonical.category and ingredient.category:
                canonical.category = ingredient.category
                canonical.save(update_fields=["category"])
            ingredient.delete()
            merged += 1

    messages.success(request, f"Merged {merged} ingredient(s) into {canonical.name}.")
    return redirect("ingredient_list")

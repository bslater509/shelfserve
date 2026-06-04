from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import RecipeForm, SettingsForm, SupermarketForm
from .models import (
    AppSetting,
    Ingredient,
    MEAL_SLOTS,
    MealPlanEntry,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    Supermarket,
    SupermarketSection,
    Tag,
    Unit,
)
from .services import build_shopping_list, normalise_name, normalise_tag_name


def dashboard(request):
    today = date.today()
    settings = AppSetting.current()
    week_start = start_of_week(today, settings.week_start)
    context = {
        "recipe_count": Recipe.objects.count(),
        "supermarket_count": Supermarket.objects.count(),
        "today_entries": MealPlanEntry.objects.filter(date=today).select_related("recipe"),
        "recent_lists": ShoppingList.objects.select_related("supermarket")[:5],
        "week_start": week_start,
    }
    return render(request, "recipes/dashboard.html", context)


def recipe_list(request):
    query = request.GET.get("q", "").strip()
    recipes = Recipe.objects.prefetch_related("tags", "ingredients__ingredient")
    if query:
        recipes = recipes.filter(
            Q(title__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(ingredients__ingredient__name__icontains=query)
        ).distinct()
    return render(request, "recipes/recipe_list.html", {"recipes": recipes, "query": query})


def recipe_detail(request, pk):
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related("tags", "ingredients__ingredient"),
        pk=pk,
    )
    return render(request, "recipes/recipe_detail.html", {"recipe": recipe})


def recipe_edit(request, pk=None):
    recipe = get_object_or_404(Recipe, pk=pk) if pk else None
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        ingredient_rows = parse_ingredient_rows(request.POST)
        if form.is_valid() and ingredient_rows:
            recipe = form.save()
            save_recipe_tags(recipe, request.POST.get("tags_text", ""))
            save_recipe_ingredients(recipe, ingredient_rows)
            messages.success(request, "Recipe saved.")
            return redirect(recipe)
        if not ingredient_rows:
            messages.error(request, "Add at least one ingredient with a quantity.")
    else:
        form = RecipeForm(instance=recipe)
        if recipe:
            form.fields["tags_text"].initial = ", ".join(recipe.tags.values_list("name", flat=True))

    ingredients = list(recipe.ingredients.select_related("ingredient")) if recipe else []
    suggested_ingredients = list(Ingredient.objects.values_list("name", flat=True).distinct().order_by("name"))
    suggested_categories = list(Ingredient.objects.exclude(category="").values_list("category", flat=True).distinct().order_by("category"))
    return render(
        request,
        "recipes/recipe_form.html",
        {
            "form": form,
            "recipe": recipe,
            "ingredients": ingredients,
            "units": Unit.choices,
            "suggested_ingredients": suggested_ingredients,
            "suggested_categories": suggested_categories,
        },
    )


def planner(request):
    settings = AppSetting.current()
    selected = parse_date(request.GET.get("week")) or date.today()
    week_start = start_of_week(selected, settings.week_start)
    days = [week_start + timedelta(days=offset) for offset in range(7)]
    recipes = Recipe.objects.all()

    if request.method == "POST":
        MealPlanEntry.objects.filter(date__range=(days[0], days[-1])).delete()
        for day in days:
            for slot, _label in MEAL_SLOTS:
                recipe_id = request.POST.get(f"recipe_{day.isoformat()}_{slot}")
                servings_value = request.POST.get(f"servings_{day.isoformat()}_{slot}") or "1"
                if recipe_id:
                    recipe = get_object_or_404(Recipe, pk=recipe_id)
                    MealPlanEntry.objects.create(
                        date=day,
                        meal_slot=slot,
                        recipe=recipe,
                        servings=max(1, int(servings_value)),
                    )
        messages.success(request, "Meal plan saved.")
        return redirect(f"{reverse('planner')}?week={week_start.isoformat()}")

    entries = {
        f"{entry.date.isoformat()}_{entry.meal_slot}": entry
        for entry in MealPlanEntry.objects.filter(date__range=(days[0], days[-1])).select_related("recipe")
    }
    supermarkets = Supermarket.objects.all()
    return render(
        request,
        "recipes/planner.html",
        {
            "days": days,
            "meal_slots": MEAL_SLOTS,
            "recipes": recipes,
            "entries": entries,
            "supermarkets": supermarkets,
            "week_start": week_start,
            "previous_week": week_start - timedelta(days=7),
            "next_week": week_start + timedelta(days=7),
        },
    )


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
    shopping_list = build_shopping_list(supermarket, week_start, plan_entries)
    messages.success(request, "Shopping list generated.")
    return redirect("shopping_list_detail", pk=shopping_list.pk)


def shopping_list_detail(request, pk):
    shopping_list = get_object_or_404(
        ShoppingList.objects.select_related("supermarket").prefetch_related("items"),
        pk=pk,
    )
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
    ingredient_categories = list(Ingredient.objects.exclude(category="").values_list("category", flat=True).distinct())
    suggested_categories = sorted(list(set(supermarket_sections + ingredient_categories)))

    return render(
        request,
        "recipes/shopping_list_detail.html",
        {
            "shopping_list": shopping_list,
            "grouped_items": grouped_items,
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
        notes=request.POST.get("notes", "").strip()
    )
    messages.success(request, f"Added {ingredient_name} to shopping list.")
    return redirect("shopping_list_detail", pk=pk)


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

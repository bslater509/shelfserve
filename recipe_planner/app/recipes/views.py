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


def recipe_list(request):
    query = request.GET.get("q", "").strip()
    selected_tag = normalise_tag_name(request.GET.get("tag", ""))
    selected_filter = request.GET.get("filter", "").strip()
    sort = request.GET.get("sort", "title")
    sort_options = {
        "title": "Title A-Z",
        "newest": "Newest first",
        "updated": "Recently updated",
        "servings": "Servings",
    }
    sort_ordering = {
        "title": ("title",),
        "newest": ("-created_at", "title"),
        "updated": ("-updated_at", "title"),
        "servings": ("servings", "title"),
    }
    if sort not in sort_options:
        sort = "title"
    recipes = Recipe.objects.prefetch_related("tags", "ingredients__ingredient")
    if query:
        recipes = recipes.filter(
            Q(title__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(ingredients__ingredient__name__icontains=query)
        ).distinct()
    if selected_tag:
        recipes = recipes.filter(tags__name__iexact=selected_tag).distinct()
    if selected_filter == "favorites":
        recipes = recipes.filter(favorite=True)
    elif selected_filter == "missing_image":
        recipes = recipes.filter(image="")
    elif selected_filter == "never_cooked":
        recipes = recipes.filter(last_cooked_at__isnull=True)
    elif selected_filter == "pantry_friendly":
        pantry_names = PantryItem.objects.filter(quantity__gt=0).values_list("ingredient__name", flat=True)
        recipes = recipes.filter(ingredients__ingredient__name__in=pantry_names).distinct()
    recipes = recipes.order_by(*sort_ordering[sort])
    return render(
        request,
        "recipes/recipe_list.html",
        {
            "recipes": recipes,
            "query": query,
            "selected_tag": selected_tag,
            "sort": sort,
            "sort_options": sort_options,
            "selected_filter": selected_filter,
            "filter_options": {
                "favorites": "Favorites",
                "pantry_friendly": "Uses pantry stock",
                "never_cooked": "Never cooked",
                "missing_image": "Missing image",
            },
            "tags": Tag.objects.annotate(recipe_count=Count("recipe")).filter(recipe_count__gt=0),
        },
    )


def recipe_detail(request, pk):
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related("tags", "ingredients__ingredient"),
        pk=pk,
    )
    return render(request, "recipes/recipe_detail.html", {"recipe": recipe})


def recipe_edit(request, pk=None):
    recipe = get_object_or_404(Recipe, pk=pk) if pk else None
    imported_image_path = ""
    imported_image_url = ""
    ingredients = []
    steps = []

    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        ingredient_rows = parse_ingredient_rows(request.POST)
        step_rows = parse_step_rows(request.POST)
        if form.is_valid() and ingredient_rows and step_rows:
            recipe = form.save(commit=False)
            imported_img = valid_imported_image_path(request.POST.get("imported_image_path", ""))
            if imported_img and not request.FILES.get("image"):
                recipe.image = imported_img
            recipe.save()
            save_recipe_tags(recipe, request.POST.get("tags_text", ""))
            save_recipe_ingredients(recipe, ingredient_rows)
            save_recipe_steps(recipe, step_rows)
            messages.success(request, "Recipe saved.")
            return redirect(recipe)
            
        # Re-populate ingredients list with POST data for rendering if validation fails
        for row in ingredient_rows:
            ingredients.append({
                "ingredient": {
                    "name": row["name"],
                    "category": row["category"],
                },
                "quantity": row["quantity"],
                "unit": row["unit"],
                "note": row["note"],
            })
            
        # Re-populate steps list with POST data for rendering if validation fails
        for row in step_rows:
            steps.append({
                "text": row["text"],
                "duration_minutes": row["duration_minutes"],
            })
            
        if not ingredient_rows:
            messages.error(request, "Add at least one ingredient with a quantity.")
        if not step_rows:
            messages.error(request, "Add at least one instruction step.")
        imported_image_path = valid_imported_image_path(request.POST.get("imported_image_path", ""))
        imported_image_url = imported_image_media_url(imported_image_path)
    else:
        initial = {}
        imported_ingredients = []
        imported_steps = []
        if not recipe:
            imported = request.session.pop("imported_recipe", None)
            if imported:
                initial = {
                    "title": imported.get("title", ""),
                    "servings": imported.get("servings", 4),
                    "prep_minutes": imported.get("prep_minutes"),
                    "cook_minutes": imported.get("cook_minutes"),
                    "source_url": imported.get("source_url", ""),
                    "tags_text": ", ".join(imported.get("tags_list", [])),
                }
                imported_image_path = valid_imported_image_path(imported.get("image_path", ""))
                imported_image_url = imported_image_media_url(imported_image_path)
                for ing in imported.get("ingredients", []):
                    imported_ingredients.append({
                        "ingredient": {
                            "name": ing.get("name", ""),
                            "category": ing.get("category", ""),
                        },
                        "quantity": ing.get("quantity", "1.00"),
                        "unit": ing.get("unit", "item"),
                        "note": ing.get("note", ""),
                    })
                for step in imported.get("steps", []):
                    if isinstance(step, dict):
                        imported_steps.append({
                            "text": step.get("text", ""),
                            "duration_minutes": step.get("duration_minutes"),
                        })
                    else:
                        imported_steps.append({
                            "text": str(step),
                            "duration_minutes": None,
                        })
        
        form = RecipeForm(instance=recipe, initial=initial if not recipe else None)
        if recipe:
            form.fields["tags_text"].initial = ", ".join(recipe.tags.values_list("name", flat=True))

        if recipe:
            ingredients = list(recipe.ingredients.select_related("ingredient"))
            steps = list(recipe.steps.all().order_by("order"))
        else:
            ingredients = imported_ingredients
            steps = imported_steps

    suggested_ingredients = list(Ingredient.objects.values_list("name", flat=True).distinct().order_by("name"))
    suggested_categories = list(Ingredient.objects.exclude(category="").values_list("category", flat=True).distinct().order_by("category"))
    return render(
        request,
        "recipes/recipe_form.html",
        {
            "form": form,
            "recipe": recipe,
            "ingredients": ingredients,
            "steps": steps,
            "units": Unit.choices,
            "suggested_ingredients": suggested_ingredients,
            "suggested_categories": suggested_categories,
            "imported_image_path": imported_image_path,
            "imported_image_url": imported_image_url,
        },
    )


def recipe_import(request):
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
        raw_text = request.POST.get("raw_text", "").strip()
        
        try:
            if url:
                imported = parse_recipe_url(url)
            elif raw_text:
                imported = parse_recipe_text(raw_text)
            else:
                messages.error(request, "Please provide either a URL or raw text.")
                return render(request, "recipes/recipe_import.html")
                
            request.session["imported_recipe"] = imported
            if Recipe.objects.filter(title__iexact=imported.get("title", "")).exists():
                messages.warning(request, "A recipe with this title already exists. Review it before saving a duplicate.")
            messages.success(request, "Recipe imported successfully! Please review and save it.")
            return redirect("recipe_create")
        except Exception as e:
            messages.error(request, f"Error importing recipe: {str(e)}")
            
    return render(request, "recipes/recipe_import.html")


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
    ingredient_categories = list(Ingredient.objects.exclude(category="").values_list("category", flat=True).distinct())
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

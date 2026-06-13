from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RecipeForm
from .models import Ingredient, PantryItem, Recipe, Tag, Unit
from .services import normalise_tag_name
from .parser import get_supported_websites, parse_recipe_text, parse_recipe_url
from .view_helpers import (
    imported_image_media_url,
    parse_ingredient_rows,
    parse_step_rows,
    save_recipe_ingredients,
    save_recipe_steps,
    save_recipe_tags,
    valid_imported_image_path,
)


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
        Recipe.objects.prefetch_related("tags", "ingredients__ingredient", "steps"),
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
                from . import views as public_views

                imported = public_views.parse_recipe_url(url)
            elif raw_text:
                from . import views as public_views

                imported = public_views.parse_recipe_text(raw_text)
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
            
    return render(request, "recipes/recipe_import.html", {
        "supported_websites": get_supported_websites(),
    })

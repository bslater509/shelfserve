from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PantryItemForm
from .models import Ingredient, PantryItem
from .view_helpers import save_pantry_item_form


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

from django.contrib import admin

from .models import (
    AppSetting,
    Ingredient,
    MealPlanEntry,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    Supermarket,
    SupermarketSection,
    Tag,
)


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "servings", "updated_at")
    search_fields = ("title", "ingredients__ingredient__name", "tags__name")
    inlines = [RecipeIngredientInline]


admin.site.register(AppSetting)
admin.site.register(Tag)
admin.site.register(Ingredient)
admin.site.register(Supermarket)
admin.site.register(SupermarketSection)
admin.site.register(MealPlanEntry)
admin.site.register(ShoppingList)
admin.site.register(ShoppingListItem)


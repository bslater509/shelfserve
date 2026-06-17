from django.contrib import admin

from .models import (
    AppSetting,
    Ingredient,
    IngredientCategory,
    IngredientNormalization,
    MealPlanEntry,
    MealPlanTemplate,
    MealPlanTemplateEntry,
    PantryAdjustment,
    PantryItem,
    Recipe,
    RecipeIngredient,
    RecipeStep,
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
    list_display = ("title", "servings", "favorite", "last_cooked_at", "updated_at")
    search_fields = ("title", "ingredients__ingredient__name", "tags__name")
    inlines = [RecipeIngredientInline]


admin.site.register(AppSetting)
admin.site.register(Tag)
admin.site.register(IngredientCategory)
admin.site.register(IngredientNormalization)
admin.site.register(Supermarket)
admin.site.register(SupermarketSection)
admin.site.register(MealPlanEntry)
admin.site.register(MealPlanTemplate)
admin.site.register(MealPlanTemplateEntry)
admin.site.register(PantryItem)
admin.site.register(PantryAdjustment)
admin.site.register(RecipeStep)
admin.site.register(ShoppingList)
admin.site.register(ShoppingListItem)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "canonical")
    list_filter = ("category",)
    search_fields = ("name",)

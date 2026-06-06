from django import forms

from .models import AppSetting, PantryItem, Recipe, Supermarket, Unit


class RecipeForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        label="Tags",
        help_text="Comma-separated tags, for example quick, vegetarian, freezer.",
    )

    class Meta:
        model = Recipe
        fields = ["title", "image", "servings", "prep_minutes", "cook_minutes", "source_url", "favorite"]


class SupermarketForm(forms.ModelForm):
    class Meta:
        model = Supermarket
        fields = ["name"]


class PantryItemForm(forms.ModelForm):
    ingredient_name = forms.CharField(label="Ingredient", max_length=120)

    class Meta:
        model = PantryItem
        fields = ["ingredient_name", "quantity", "unit", "low_stock_threshold", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["ingredient_name"].initial = self.instance.ingredient.name
        self.fields["unit"].initial = self.fields["unit"].initial or Unit.ITEM


class SettingsForm(forms.ModelForm):
    class Meta:
        model = AppSetting
        fields = ["week_start"]

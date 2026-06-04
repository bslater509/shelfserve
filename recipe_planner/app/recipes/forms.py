from django import forms

from .models import AppSetting, Recipe, Supermarket


class RecipeForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        label="Tags",
        help_text="Comma-separated tags, for example quick, vegetarian, freezer.",
    )

    class Meta:
        model = Recipe
        fields = ["title", "image", "servings"]


class SupermarketForm(forms.ModelForm):
    class Meta:
        model = Supermarket
        fields = ["name"]


class SettingsForm(forms.ModelForm):
    class Meta:
        model = AppSetting
        fields = ["week_start"]


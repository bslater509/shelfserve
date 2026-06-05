from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("recipes/", views.recipe_list, name="recipe_list"),
    path("recipes/import/", views.recipe_import, name="recipe_import"),
    path("recipes/new/", views.recipe_edit, name="recipe_create"),
    path("recipes/<int:pk>/", views.recipe_detail, name="recipe_detail"),
    path("recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("pantry/", views.pantry_list, name="pantry_list"),
    path("pantry/items/<int:pk>/edit/", views.edit_pantry_item, name="edit_pantry_item"),
    path("pantry/items/<int:pk>/delete/", views.delete_pantry_item, name="delete_pantry_item"),
    path("planner/", views.planner, name="planner"),
    path("planner/entries/<int:pk>/cook/", views.cook_planner_entry, name="cook_planner_entry"),
    path("planner/entries/<int:pk>/undo-cooked/", views.undo_cook_planner_entry, name="undo_cook_planner_entry"),
    path("shopping/generate/", views.generate_shopping_list, name="generate_shopping_list"),
    path("shopping/<int:pk>/", views.shopping_list_detail, name="shopping_list_detail"),
    path("shopping/<int:pk>/add-item/", views.add_shopping_item, name="add_shopping_item"),
    path("shopping/<int:pk>/regenerate/", views.regenerate_existing_shopping_list, name="regenerate_shopping_list"),
    path("shopping/items/<int:pk>/edit/", views.edit_shopping_item, name="edit_shopping_item"),
    path("shopping/items/<int:pk>/delete/", views.delete_shopping_item, name="delete_shopping_item"),
    path("shopping/items/<int:pk>/toggle/", views.toggle_shopping_item, name="toggle_shopping_item"),
    path("supermarkets/", views.supermarket_list, name="supermarket_list"),
    path("supermarkets/<int:pk>/", views.supermarket_detail, name="supermarket_detail"),
    path("settings/", views.settings_view, name="settings"),
]

from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("recipes/", views.recipe_list, name="recipe_list"),
    path("recipes/new/", views.recipe_edit, name="recipe_create"),
    path("recipes/<int:pk>/", views.recipe_detail, name="recipe_detail"),
    path("recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("planner/", views.planner, name="planner"),
    path("shopping/generate/", views.generate_shopping_list, name="generate_shopping_list"),
    path("shopping/<int:pk>/", views.shopping_list_detail, name="shopping_list_detail"),
    path("shopping/<int:pk>/add-item/", views.add_shopping_item, name="add_shopping_item"),
    path("shopping/items/<int:pk>/toggle/", views.toggle_shopping_item, name="toggle_shopping_item"),
    path("supermarkets/", views.supermarket_list, name="supermarket_list"),
    path("supermarkets/<int:pk>/", views.supermarket_detail, name="supermarket_detail"),
    path("settings/", views.settings_view, name="settings"),
]


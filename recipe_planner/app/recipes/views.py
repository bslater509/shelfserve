"""Compatibility import surface for recipe view callables."""

from .parser import get_supported_websites, parse_recipe_text, parse_recipe_url
from .views_dashboard import dashboard
from .views_pantry import delete_pantry_item, edit_pantry_item, pantry_list
from .views_planner import (
    cook_planner_entry,
    delete_meal_plan_template,
    planner,
    undo_cook_planner_entry,
)
from .views_recipes import recipe_detail, recipe_edit, recipe_import, recipe_list
from .views_shopping import (
    add_shopping_item,
    delete_shopping_item,
    edit_shopping_item,
    generate_shopping_list,
    regenerate_existing_shopping_list,
    restock_shopping_list,
    shopping_list_detail,
    toggle_shopping_item,
)
from .views_supermarkets import settings_view, supermarket_detail, supermarket_list

__all__ = [
    "add_shopping_item",
    "cook_planner_entry",
    "get_supported_websites",
    "dashboard",
    "delete_meal_plan_template",
    "delete_pantry_item",
    "delete_shopping_item",
    "edit_pantry_item",
    "edit_shopping_item",
    "generate_shopping_list",
    "pantry_list",
    "planner",
    "parse_recipe_text",
    "parse_recipe_url",
    "recipe_detail",
    "recipe_edit",
    "recipe_import",
    "recipe_list",
    "regenerate_existing_shopping_list",
    "restock_shopping_list",
    "settings_view",
    "shopping_list_detail",
    "supermarket_detail",
    "supermarket_list",
    "toggle_shopping_item",
    "undo_cook_planner_entry",
]

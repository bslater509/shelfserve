import io
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import (
    AppSetting,
    Ingredient,
    MealPlanEntry,
    PantryAdjustment,
    PantryItem,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    Supermarket,
    SupermarketSection,
    Tag,
    Unit,
)
from .services import build_shopping_list
from .views import start_of_week


MEDIA_ROOT = tempfile.mkdtemp()


class FakeHeaders:
    def __init__(self, content_type):
        self.content_type = content_type

    def get(self, name, default=None):
        if name.lower() == "content-type" and self.content_type:
            return self.content_type
        return default

    def get_content_type(self):
        return self.content_type


class FakeUrlOpenResponse:
    def __init__(self, content_type, payload):
        self.headers = FakeHeaders(content_type)
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        return self.payload


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class RecipePlannerTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_recipe_create_with_image_tags_and_structured_ingredients(self):
        image = SimpleUploadedFile(
            "toast.gif",
            b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )

        response = self.client.post(
            reverse("recipe_create"),
            {
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick, vegetarian",
                "ingredient_name": ["Bread", "Baked beans"],
                "ingredient_quantity": ["4", "415"],
                "ingredient_unit": [Unit.ITEM, Unit.GRAM],
                "ingredient_category": ["Bakery", "Tins"],
                "ingredient_note": ["slices", ""],
                "image": image,
            },
        )

        recipe = Recipe.objects.get(title="Beans on toast")
        self.assertRedirects(response, recipe.get_absolute_url())
        self.assertTrue(recipe.image.name.startswith("recipes/"))
        self.assertEqual(recipe.tags.count(), 2)
        self.assertEqual(recipe.ingredients.count(), 2)
        self.assertEqual(Ingredient.objects.get(name="Bread").category, "Bakery")

    def test_recipe_create_accepts_home_assistant_ingress_origin(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/3975db7c_shelfserve"
        origin = "http://192.168.0.94:8123"

        form_response = client.get(
            reverse("recipe_create"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("recipe_create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick",
                "ingredient_name": ["Bread"],
                "ingredient_quantity": ["4"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Bakery"],
                "ingredient_note": ["slices"],
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Recipe.objects.filter(title="Beans on toast").exists())

    def test_recipe_create_accepts_origin_without_ingress_header(self):
        client = Client(enforce_csrf_checks=True)
        origin = "http://192.168.0.94:8123"

        form_response = client.get(
            reverse("recipe_create"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("recipe_create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick",
                "ingredient_name": ["Bread"],
                "ingredient_quantity": ["4"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Bakery"],
                "ingredient_note": ["slices"],
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Recipe.objects.filter(title="Beans on toast").exists())

    def test_recipe_create_accepts_https_home_assistant_ingress_origin(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/3975db7c_shelfserve"
        origin = "https://homeassistant.example.com"

        form_response = client.get(
            reverse("recipe_create"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("recipe_create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick",
                "ingredient_name": ["Bread"],
                "ingredient_quantity": ["4"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Bakery"],
                "ingredient_note": ["slices"],
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Recipe.objects.filter(title="Beans on toast").exists())

    def test_recipe_create_accepts_https_home_assistant_ingress_referer(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/3975db7c_shelfserve"
        referer = f"https://homeassistant.example.com{ingress_path}{reverse('recipe_create')}"

        form_response = client.get(
            reverse("recipe_create"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_REFERER=referer,
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("recipe_create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick",
                "ingredient_name": ["Bread"],
                "ingredient_quantity": ["4"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Bakery"],
                "ingredient_note": ["slices"],
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_REFERER=referer,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Recipe.objects.filter(title="Beans on toast").exists())

    def test_recipe_create_accepts_proxy_https_without_origin_or_referer(self):
        client = Client(enforce_csrf_checks=True)

        form_response = client.get(
            reverse("recipe_create"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("recipe_create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "title": "Beans on toast",
                "servings": "2",
                "step_text": ["Toast bread.", "Add beans."],
                "step_duration": ["", ""],
                "tags_text": "quick",
                "ingredient_name": ["Bread"],
                "ingredient_quantity": ["4"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Bakery"],
                "ingredient_note": ["slices"],
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Recipe.objects.filter(title="Beans on toast").exists())

    def test_supermarket_create_accepts_home_assistant_ingress_origin(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/3975db7c_shelfserve"
        origin = "http://192.168.0.94:8123"

        form_response = client.get(
            reverse("supermarket_list"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("supermarket_list"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "name": "Tesco",
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN=origin,
        )

        supermarket = Supermarket.objects.get(name="Tesco")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{ingress_path}{reverse('supermarket_detail', args=[supermarket.pk])}")

    def test_supermarket_create_accepts_home_assistant_ingress_null_origin(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/api/hassio_ingress/ETrznauquxiTbiOHgkNL6KeWBz1tFwA7jC1qW_v2Xeg"

        form_response = client.get(
            reverse("supermarket_list"),
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.94:8123",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN="null",
        )
        self.assertEqual(form_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("supermarket_list"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "name": "Tesco",
            },
            HTTP_HOST="192.168.0.103:8099",
            HTTP_X_INGRESS_PATH=ingress_path,
            HTTP_X_FORWARDED_HOST="192.168.0.94:8123",
            HTTP_X_FORWARDED_PROTO="http",
            HTTP_ORIGIN="null",
        )

        supermarket = Supermarket.objects.get(name="Tesco")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{ingress_path}{reverse('supermarket_detail', args=[supermarket.pk])}")

    def test_csrf_failure_debug_logs_ingress_context_without_secrets(self):
        client = Client(enforce_csrf_checks=True)
        ingress_path = "/3975db7c_shelfserve"
        origin = "http://192.168.0.94:8123"
        cookie_secret = "a" * 32
        client.cookies[django_settings.CSRF_COOKIE_NAME] = cookie_secret

        with self.assertLogs("shelfserve.csrf", level="DEBUG") as logs:
            response = client.post(
                reverse("supermarket_list"),
                {
                    "name": "Tesco",
                },
                HTTP_HOST="192.168.0.103:8099",
                HTTP_X_INGRESS_PATH=ingress_path,
                HTTP_X_FORWARDED_HOST="192.168.0.103:8099",
                HTTP_X_FORWARDED_PROTO="http",
                HTTP_ORIGIN=origin,
            )

        self.assertEqual(response.status_code, 403)
        log_output = "\n".join(logs.output)
        self.assertIn("CSRF failure diagnostics", log_output)
        self.assertIn("CSRF token missing", log_output)
        self.assertIn("'method': 'POST'", log_output)
        self.assertIn(f"'x_ingress_path': '{ingress_path}'", log_output)
        self.assertIn(f"'origin': '{origin}'", log_output)
        self.assertIn("'x_forwarded_host': '192.168.0.94:8123'", log_output)
        self.assertIn("'x_forwarded_proto': 'http'", log_output)
        self.assertIn("'script_name': '/3975db7c_shelfserve'", log_output)
        self.assertIn("'csrf_cookie_present': True", log_output)
        self.assertIn("'submitted_csrf_field_present': False", log_output)
        self.assertIn("'post_field_names': ['name']", log_output)
        self.assertNotIn(cookie_secret, log_output)
        self.assertNotIn("Tesco", log_output)

    def test_supermarket_aisle_order_save_is_scoped_to_one_supermarket(self):
        tesco = Supermarket.objects.create(name="Tesco")
        tesco_fruit = SupermarketSection.objects.create(supermarket=tesco, name="Fruit & veg", order=0)
        tesco_bakery = SupermarketSection.objects.create(supermarket=tesco, name="Bakery", order=1)
        asda = Supermarket.objects.create(name="Asda")
        SupermarketSection.objects.create(supermarket=asda, name="Bakery", order=0)
        SupermarketSection.objects.create(supermarket=asda, name="Fruit & veg", order=1)

        response = self.client.post(
            reverse("supermarket_detail", args=[tesco.pk]),
            {
                "name": "Tesco",
                "sections": ["Bakery", "Fruit & veg", "Tins", "Bakery"],
            },
        )

        self.assertRedirects(response, reverse("supermarket_detail", args=[tesco.pk]))
        self.assertEqual(
            list(tesco.sections.values_list("name", "order", "pk")),
            [
                ("Bakery", 0, tesco_bakery.pk),
                ("Fruit & veg", 1, tesco_fruit.pk),
                ("Tins", 2, SupermarketSection.objects.get(supermarket=tesco, name="Tins").pk),
            ],
        )
        self.assertEqual(
            list(asda.sections.values_list("name", "order")),
            [
                ("Bakery", 0),
                ("Fruit & veg", 1),
            ],
        )

    def test_supermarket_rename_and_aisle_deduplication(self):
        tesco = Supermarket.objects.create(name="Tesco Original")
        response = self.client.post(
            reverse("supermarket_detail", args=[tesco.pk]),
            {
                "name": "Tesco Renamed",
                "sections": ["Bakery", "", "bakery", "  Dairy  ", "Bakery"],
            },
        )
        self.assertRedirects(response, reverse("supermarket_detail", args=[tesco.pk]))
        tesco.refresh_from_db()
        self.assertEqual(tesco.name, "Tesco Renamed")
        # Empty and duplicate sections should be ignored/deduplicated (case-insensitive)
        self.assertEqual(
            list(tesco.sections.values_list("name", "order")),
            [
                ("Bakery", 0),
                ("Dairy", 1),
            ],
        )

    def test_week_start_uses_configurable_setting(self):
        settings = AppSetting.current()
        settings.week_start = 6
        settings.save()

        self.assertEqual(start_of_week(date(2026, 6, 4), settings.week_start).isoformat(), "2026-05-31")

    def test_shopping_list_scales_combines_and_sorts_by_supermarket(self):
        fruit = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        flour = Ingredient.objects.create(name="Plain flour", category="Bakery")
        recipe = Recipe.objects.create(title="Pizza", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=fruit, quantity=Decimal("500"), unit=Unit.GRAM, order=1)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=fruit, quantity=Decimal("2"), unit=Unit.ITEM, order=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=flour, quantity=Decimal("0.5"), unit=Unit.KILOGRAM, order=3)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=4)

        tesco = Supermarket.objects.create(name="Tesco")
        SupermarketSection.objects.create(supermarket=tesco, name="Fruit & veg", order=0)
        SupermarketSection.objects.create(supermarket=tesco, name="Bakery", order=1)
        asda = Supermarket.objects.create(name="Asda")
        SupermarketSection.objects.create(supermarket=asda, name="Bakery", order=0)
        SupermarketSection.objects.create(supermarket=asda, name="Fruit & veg", order=1)

        tesco_list = build_shopping_list(tesco, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        tesco_items = list(tesco_list.items.values_list("section_name", "ingredient_name", "quantity", "unit"))
        self.assertEqual(tesco_items[0][0], "Fruit & veg")
        self.assertEqual(tesco_items[0][1], "Tomatoes")
        self.assertEqual(tesco_items[0][2], Decimal("1000.00"))
        self.assertEqual(tesco_items[0][3], Unit.GRAM)
        self.assertEqual(tesco_items[1][1], "Tomatoes")
        self.assertEqual(tesco_items[1][3], Unit.ITEM)
        self.assertEqual(tesco_items[2][0], "Bakery")
        self.assertEqual(tesco_items[2][2], Decimal("1000.00"))
        self.assertEqual(tesco_items[2][3], Unit.GRAM)

        asda_list = build_shopping_list(asda, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        self.assertEqual(asda_list.items.first().section_name, "Bakery")
        self.assertEqual(ShoppingListItem.objects.filter(shopping_list=asda_list).count(), 3)

    def test_pantry_item_create_edit_and_delete(self):
        self.assertEqual(self.client.get(reverse("pantry_list")).status_code, 200)

        response = self.client.post(
            reverse("pantry_list"),
            {
                "ingredient_name": "Plain flour",
                "quantity": "1.5",
                "unit": Unit.KILOGRAM,
                "note": "Cupboard",
            },
        )
        self.assertRedirects(response, reverse("pantry_list"))
        pantry_item = PantryItem.objects.get(ingredient__name="Plain flour")
        self.assertEqual(pantry_item.quantity, Decimal("1.50"))
        self.assertEqual(pantry_item.unit, Unit.KILOGRAM)

        response = self.client.post(
            reverse("edit_pantry_item", args=[pantry_item.pk]),
            {
                "ingredient_name": "Plain flour",
                "quantity": "2",
                "unit": Unit.KILOGRAM,
                "note": "Restocked",
            },
        )
        self.assertRedirects(response, reverse("pantry_list"))
        pantry_item.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("2.00"))
        self.assertEqual(pantry_item.note, "Restocked")

        response = self.client.post(reverse("delete_pantry_item", args=[pantry_item.pk]))
        self.assertRedirects(response, reverse("pantry_list"))
        self.assertFalse(PantryItem.objects.filter(pk=pantry_item.pk).exists())

    def test_shopping_list_subtracts_matching_pantry_stock(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("0.60"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("1000"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        item = shopping_list.items.get(ingredient_name="Tomatoes")

        self.assertEqual(item.quantity, Decimal("400.00"))
        self.assertEqual(item.unit, Unit.GRAM)
        self.assertIn("pantry used: 600 g", item.notes)
        self.assertEqual(PantryItem.objects.get(pk=PantryItem.objects.first().pk).quantity, Decimal("0.60"))

    def test_shopping_list_omits_items_fully_covered_by_pantry(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))

        self.assertEqual(shopping_list.items.count(), 0)

    def test_shopping_list_does_not_subtract_incompatible_pantry_units(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.ITEM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        item = shopping_list.items.get(ingredient_name="Tomatoes")

        self.assertEqual(item.quantity, Decimal("500.00"))
        self.assertEqual(item.unit, Unit.GRAM)

    def test_toggle_shopping_item_ajax(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
            checked=False
        )

        response = self.client.post(
            reverse("toggle_shopping_item", args=[item.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": item.pk, "checked": True})
        
        item.refresh_from_db()
        self.assertTrue(item.checked)

    def test_add_custom_shopping_item(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        SupermarketSection.objects.create(supermarket=supermarket, name="Bakery", order=0)
        SupermarketSection.objects.create(supermarket=supermarket, name="Dairy", order=1)
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))

        # Test adding custom item in an existing section ("Dairy")
        response = self.client.post(
            reverse("add_shopping_item", args=[shopping_list.pk]),
            {
                "ingredient_name": "Milk",
                "quantity": "2",
                "unit": Unit.LITRE,
                "section_name": "Dairy",
                "notes": "Organic"
            }
        )
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        
        item = ShoppingListItem.objects.get(shopping_list=shopping_list, ingredient_name="Milk")
        self.assertEqual(item.quantity, Decimal("2.00"))
        self.assertEqual(item.unit, Unit.LITRE)
        self.assertEqual(item.section_name, "Dairy")
        self.assertEqual(item.section_order, 1)
        self.assertEqual(item.notes, "Organic")

        # Test adding custom item in a non-existent section
        self.client.post(
            reverse("add_shopping_item", args=[shopping_list.pk]),
            {
                "ingredient_name": "Paper towels",
                "quantity": "1",
                "unit": Unit.ITEM,
                "section_name": "Household",
                "notes": ""
            }
        )
        item2 = ShoppingListItem.objects.get(shopping_list=shopping_list, ingredient_name="Paper towels")
        self.assertEqual(item2.section_name, "Household")
        self.assertEqual(item2.section_order, 9999)
        self.assertTrue(item2.is_custom)

    def test_regenerate_shopping_list_preserves_checked_generated_items_and_custom_items(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        recipe_ingredient = RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=tomatoes,
            quantity=Decimal("100"),
            unit=Unit.GRAM,
            note="ripe",
        )
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")
        SupermarketSection.objects.create(supermarket=supermarket, name="Fruit & veg", order=0)
        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        generated_item = shopping_list.items.get(ingredient_name="Tomatoes")
        generated_item.checked = True
        generated_item.save(update_fields=["checked"])
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Dairy",
            section_order=1,
            ingredient_name="Milk",
            quantity=Decimal("1"),
            unit=Unit.LITRE,
            checked=True,
            is_custom=True,
        )

        recipe_ingredient.quantity = Decimal("200")
        recipe_ingredient.note = "cherry"
        recipe_ingredient.save(update_fields=["quantity", "note"])
        response = self.client.post(reverse("regenerate_shopping_list", args=[shopping_list.pk]))

        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        regenerated_item = shopping_list.items.get(ingredient_name="Tomatoes")
        self.assertEqual(regenerated_item.quantity, Decimal("200.00"))
        self.assertEqual(regenerated_item.notes, "cherry")
        self.assertTrue(regenerated_item.checked)
        custom_item = shopping_list.items.get(ingredient_name="Milk")
        self.assertTrue(custom_item.is_custom)
        self.assertTrue(custom_item.checked)

    def test_mark_planned_meal_cooked_reduces_pantry_once_and_undo_restores(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        pantry_item = PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date=date(2026, 6, 1), meal_slot="dinner", recipe=recipe, servings=2)

        response = self.client.post(reverse("cook_planner_entry", args=[entry.pk]))
        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        pantry_item.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("0.50"))
        self.assertIsNotNone(entry.pantry_consumed_at)
        self.assertEqual(PantryAdjustment.objects.filter(meal_plan_entry=entry).count(), 1)

        self.client.post(reverse("cook_planner_entry", args=[entry.pk]))
        pantry_item.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("0.50"))

        response = self.client.post(reverse("undo_cook_planner_entry", args=[entry.pk]))
        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        pantry_item.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("1.00"))
        self.assertIsNone(entry.pantry_consumed_at)
        self.assertFalse(PantryAdjustment.objects.filter(meal_plan_entry=entry).exists())

    def test_saving_planner_change_restores_pantry_for_removed_cooked_meal(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category="Fruit & veg")
        pantry_item = PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date=date(2026, 6, 1), meal_slot="dinner", recipe=recipe, servings=2)
        self.client.post(reverse("cook_planner_entry", args=[entry.pk]))
        pantry_item.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("0.50"))

        response = self.client.post(reverse("planner") + "?week=2026-06-01", {})

        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        pantry_item.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("1.00"))
        self.assertFalse(MealPlanEntry.objects.filter(pk=entry.pk).exists())

    def test_edit_shopping_item_updates_validated_fields_and_section_order(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        SupermarketSection.objects.create(supermarket=supermarket, name="Bakery", order=0)
        SupermarketSection.objects.create(supermarket=supermarket, name="Dairy", order=1)
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            section_order=0,
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
        )

        response = self.client.post(
            reverse("edit_shopping_item", args=[item.pk]),
            {
                "ingredient_name": "Milk",
                "quantity": "2",
                "unit": Unit.LITRE,
                "section_name": "Dairy",
                "notes": "Organic",
            },
        )

        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        item.refresh_from_db()
        self.assertEqual(item.ingredient_name, "Milk")
        self.assertEqual(item.quantity, Decimal("2.00"))
        self.assertEqual(item.unit, Unit.LITRE)
        self.assertEqual(item.section_name, "Dairy")
        self.assertEqual(item.section_order, 1)
        self.assertEqual(item.notes, "Organic")

    def test_delete_shopping_item_removes_only_target_item(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        bread = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
        )
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Dairy",
            ingredient_name="Milk",
            quantity=Decimal("1"),
            unit=Unit.LITRE,
        )

        response = self.client.post(reverse("delete_shopping_item", args=[bread.pk]))

        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        self.assertFalse(ShoppingListItem.objects.filter(pk=bread.pk).exists())
        self.assertEqual(shopping_list.items.count(), 1)

    def test_dashboard_shows_recent_list_completion_count(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
            checked=True,
        )
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Dairy",
            ingredient_name="Milk",
            quantity=Decimal("1"),
            unit=Unit.LITRE,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1/2")

    def test_dashboard_uses_clean_list_separator(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&middot;", html=False)
        self.assertNotContains(response, "Â·")

    def test_recipe_list_filters_by_tag(self):
        quick = Tag.objects.create(name="quick")
        dinner = Tag.objects.create(name="dinner")
        toast = Recipe.objects.create(title="Beans on toast", servings=2)
        toast.tags.add(quick)
        stew = Recipe.objects.create(title="Slow stew", servings=4)
        stew.tags.add(dinner)

        response = self.client.get(reverse("recipe_list") + "?tag=quick")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Beans on toast")
        self.assertNotContains(response, "Slow stew")
        self.assertEqual(list(response.context["recipes"]), [toast])

    def test_recipe_list_combines_search_and_tag_filters(self):
        quick = Tag.objects.create(name="quick")
        Recipe.objects.create(title="Quick curry", servings=2).tags.add(quick)
        Recipe.objects.create(title="Quick pasta", servings=2)

        response = self.client.get(reverse("recipe_list") + "?q=quick&tag=quick")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick curry")
        self.assertNotContains(response, "Quick pasta")

    def test_planner_links_latest_shopping_list_for_selected_week(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))

        response = self.client.get(reverse("planner") + "?week=2026-06-01")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        self.assertContains(response, "Open latest Tesco list")

    def test_parse_ingredient_line(self):
        from .parser import parse_ingredient_line
        
        # Test fractions
        res = parse_ingredient_line("1/2 cup flour, sifted")
        self.assertEqual(res["name"], "flour")
        self.assertEqual(res["quantity"], "0.50")
        self.assertEqual(res["unit"], Unit.ITEM)
        self.assertEqual(res["note"], "cup, sifted")
        
        # Test unicode fractions
        res2 = parse_ingredient_line("1\u00bd tsp salt")
        self.assertEqual(res2["name"], "salt")
        self.assertEqual(res2["quantity"], "1.50")
        self.assertEqual(res2["unit"], Unit.TEASPOON)

        res4 = parse_ingredient_line("\u00bd cup flour")
        self.assertEqual(res4["name"], "flour")
        self.assertEqual(res4["quantity"], "0.50")
        self.assertEqual(res4["note"], "cup")

        res5 = parse_ingredient_line("\u00bc tsp spice")
        self.assertEqual(res5["name"], "spice")
        self.assertEqual(res5["quantity"], "0.25")
        self.assertEqual(res5["unit"], Unit.TEASPOON)
        
        # Test standard decimal & category lookup
        Ingredient.objects.create(name="chicken breast", category="Meat")
        res3 = parse_ingredient_line("500.50g chicken breast (skinless)")
        self.assertEqual(res3["name"], "chicken breast")
        self.assertEqual(res3["quantity"], "500.50")
        self.assertEqual(res3["unit"], Unit.GRAM)
        self.assertEqual(res3["note"], "skinless")
        self.assertEqual(res3["category"], "Meat")

    def test_parse_recipe_text(self):
        from .parser import parse_recipe_text
        raw_text = (
            "Ingredients\n"
            "2 eggs\n"
            "1 tbsp butter\n"
            "Instructions\n"
            "Melt butter.\n"
            "Fry eggs.\n"
        )
        res = parse_recipe_text(raw_text)
        self.assertEqual(res["title"], "Imported Recipe")
        self.assertEqual(len(res["ingredients"]), 2)
        self.assertEqual(res["ingredients"][0]["name"], "eggs")
        self.assertEqual(res["ingredients"][0]["quantity"], "2.00")
        self.assertEqual(res["steps"][0]["text"], "Melt butter.")

    def test_recipe_import_views_and_prepopulation(self):
        # 1. Test POST to recipe_import view with raw text
        mock_data = {
            "title": "Mocked Egg",
            "servings": 2,
            "steps": [
                {"text": "Crack and fry.", "duration_minutes": 1}
            ],
            "ingredients": [
                {"name": "egg", "quantity": "2.00", "unit": "item", "note": "large", "category": "Dairy"}
            ],
            "tags_list": ["easy"],
            "image_path": "recipes/imported_mock.jpg"
        }
        with patch("recipes.views.parse_recipe_text", return_value=mock_data) as mock_parse:
            response = self.client.post(
                reverse("recipe_import"),
                {"raw_text": "2 large eggs\nCrack and fry."}
            )
            mock_parse.assert_called_once()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], reverse("recipe_create"))
            
        # Verify it's in the session
        self.assertEqual(self.client.session["imported_recipe"], mock_data)
        
        # 2. Test GET to recipe_create view (prepopulation)
        get_response = self.client.get(reverse("recipe_create"))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Mocked Egg")
        self.assertContains(get_response, "recipes/imported_mock.jpg")
        self.assertContains(get_response, 'src="/media/recipes/imported_mock.jpg"')
        
        # The session variable should be cleared now
        self.assertNotIn("imported_recipe", self.client.session)
        
        # 3. Test saving the prepopulated recipe (including imported image)
        post_response = self.client.post(
            reverse("recipe_create"),
            {
                "title": "Mocked Egg",
                "servings": "2",
                "step_text": ["Crack and fry."],
                "step_duration": ["1"],
                "tags_text": "easy",
                "ingredient_name": ["egg"],
                "ingredient_quantity": ["2.00"],
                "ingredient_unit": [Unit.ITEM],
                "ingredient_category": ["Dairy"],
                "ingredient_note": ["large"],
                "imported_image_path": "recipes/imported_mock.jpg",
            }
        )
        recipe = Recipe.objects.get(title="Mocked Egg")
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response["Location"], recipe.get_absolute_url())
        self.assertEqual(recipe.image.name, "recipes/imported_mock.jpg")
        self.assertEqual(recipe.ingredients.count(), 1)

    def test_imported_image_preview_uses_ingress_media_url(self):
        session = self.client.session
        session["imported_recipe"] = {
            "title": "Mocked Soup",
            "servings": 2,
            "steps": [{"text": "Warm through.", "duration_minutes": None}],
            "ingredients": [{"name": "stock", "quantity": "1.00", "unit": "item", "note": "", "category": ""}],
            "tags_list": ["easy"],
            "image_path": "recipes/imported_mock.jpg",
        }
        session.save()

        response = self.client.get(
            reverse("recipe_create"),
            HTTP_X_INGRESS_PATH="/3975db7c_shelfserve",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="/3975db7c_shelfserve/media/recipes/imported_mock.jpg"')

    def test_download_recipe_image_saves_verified_image(self):
        from .parser import download_recipe_image

        image_bytes = self.make_image_bytes()

        with tempfile.TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                patch("recipes.parser.urllib.request.urlopen", return_value=FakeUrlOpenResponse("image/png", image_bytes)),
            ):
                image_path = download_recipe_image("https://example.com/recipe.png")

            self.assertTrue(image_path.startswith("recipes/imported_"))
            self.assertTrue(image_path.endswith(".png"))
            self.assertTrue(os.path.exists(os.path.join(media_root, image_path)))

    def test_download_recipe_image_rejects_non_image_content_type(self):
        from .parser import download_recipe_image

        with tempfile.TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                patch("recipes.parser.urllib.request.urlopen", return_value=FakeUrlOpenResponse("text/html", b"<html></html>")),
            ):
                image_path = download_recipe_image("https://example.com/recipe")

            self.assertEqual(image_path, "")
            self.assertFalse(os.path.exists(os.path.join(media_root, "recipes")))

    def test_download_recipe_image_rejects_oversized_response(self):
        from .parser import download_recipe_image

        with tempfile.TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                patch("recipes.parser.MAX_RECIPE_IMAGE_BYTES", 8),
                patch("recipes.parser.urllib.request.urlopen", return_value=FakeUrlOpenResponse("image/png", b"x" * 9)),
            ):
                image_path = download_recipe_image("https://example.com/recipe.png")

            self.assertEqual(image_path, "")
            self.assertFalse(os.path.exists(os.path.join(media_root, "recipes")))

    def test_download_recipe_image_rejects_invalid_image_bytes(self):
        from .parser import download_recipe_image

        with tempfile.TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                patch("recipes.parser.urllib.request.urlopen", return_value=FakeUrlOpenResponse("image/png", b"not an image")),
            ):
                image_path = download_recipe_image("https://example.com/recipe.png")

            self.assertEqual(image_path, "")
            self.assertFalse(os.path.exists(os.path.join(media_root, "recipes")))

    def make_image_bytes(self):
        buffer = io.BytesIO()
        image = Image.new("RGB", (1, 1), color="white")
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_extract_step_duration(self):
        from .parser import extract_step_duration
        self.assertEqual(extract_step_duration("Bake for 45 minutes at 180C"), 45)
        self.assertEqual(extract_step_duration("Simmer for 1 hour"), 60)
        self.assertEqual(extract_step_duration("Boil for 1 hr and 15 mins"), 75)
        self.assertIsNone(extract_step_duration("Mix ingredients together"))

    def test_recipe_create_saves_structured_steps_and_durations(self):
        response = self.client.post(
            reverse("recipe_create"),
            {
                "title": "Test recipe with timers",
                "servings": "4",
                "tags_text": "timer",
                "ingredient_name": ["Sugar"],
                "ingredient_quantity": ["100"],
                "ingredient_unit": [Unit.GRAM],
                "ingredient_category": ["Baking"],
                "ingredient_note": [""],
                "step_text": ["Preheat oven.", "Bake for 30 minutes."],
                "step_duration": ["", "30"],
            },
        )
        recipe = Recipe.objects.get(title="Test recipe with timers")
        self.assertRedirects(response, recipe.get_absolute_url())
        self.assertEqual(recipe.steps.count(), 2)
        step1 = recipe.steps.get(order=0)
        step2 = recipe.steps.get(order=1)
        self.assertEqual(step1.text, "Preheat oven.")
        self.assertIsNone(step1.duration_minutes)
        self.assertEqual(step2.text, "Bake for 30 minutes.")
        self.assertEqual(step2.duration_minutes, 30)

    def test_planner_copy_week_preview(self):
        settings = AppSetting.current()
        settings.week_start = 0  # Monday
        settings.save()

        recipe = Recipe.objects.create(title="Tacos", servings=4)
        
        # Source week: June 1st, 2026 (Monday)
        source_date = date(2026, 6, 1)
        MealPlanEntry.objects.create(date=source_date, meal_slot="dinner", recipe=recipe, servings=4)

        # Target week: June 8th, 2026 (Monday)
        target_date = date(2026, 6, 8)

        # Send GET request with copy_from parameter
        response = self.client.get(
            reverse("planner") + f"?week=2026-06-08&copy_from=2026-06-01"
        )
        self.assertEqual(response.status_code, 200)

        # Verify that context includes the cloned entry mapped to the target date
        entries = response.context["entries"]
        key = f"2026-06-08_dinner"
        self.assertIn(key, entries)
        self.assertEqual(entries[key].recipe_id, recipe.pk)
        self.assertEqual(entries[key].servings, 4)

        # Verify that no entries were actually saved in the DB for the target week yet
        self.assertFalse(MealPlanEntry.objects.filter(date=target_date).exists())

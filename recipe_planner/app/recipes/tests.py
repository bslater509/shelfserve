import io
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

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
    Unit,
)
from .parser import (
    parse_ingredient_line,
    parse_recipe_text,
    parse_recipe_url,
    parse_servings,
    scraper_minutes,
    extract_step_duration,
    get_supported_websites,
    download_recipe_image,
)
from .services import build_shopping_list, unit_bucket
from .templatetags.recipe_extras import smart_quantity_display, shopping_item_display
from .view_helpers import start_of_week


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
    @staticmethod
    def _cat(name):
        return IngredientCategory.objects.get_or_create(name=name)[0]

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
        self.assertEqual(Ingredient.objects.get(name="Bread").category.name, "Bakery")

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
        fruit = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        flour = Ingredient.objects.create(name="Plain flour", category=self._cat("Bakery"))
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
                "low_stock_threshold": "0.5",
                "note": "Cupboard",
            },
        )
        self.assertRedirects(response, reverse("pantry_list"))
        pantry_item = PantryItem.objects.get(ingredient__name="Plain flour")
        self.assertEqual(pantry_item.quantity, Decimal("1.50"))
        self.assertEqual(pantry_item.unit, Unit.KILOGRAM)
        self.assertEqual(pantry_item.low_stock_threshold, Decimal("0.50"))

        response = self.client.post(
            reverse("edit_pantry_item", args=[pantry_item.pk]),
            {
                "ingredient_name": "Plain flour",
                "quantity": "2",
                "unit": Unit.KILOGRAM,
                "low_stock_threshold": "1",
                "note": "Restocked",
            },
        )
        self.assertRedirects(response, reverse("pantry_list"))
        pantry_item.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("2.00"))
        self.assertEqual(pantry_item.low_stock_threshold, Decimal("1.00"))
        self.assertEqual(pantry_item.note, "Restocked")

        response = self.client.post(reverse("delete_pantry_item", args=[pantry_item.pk]))
        self.assertRedirects(response, reverse("pantry_list"))
        self.assertFalse(PantryItem.objects.filter(pk=pantry_item.pk).exists())

    def test_dashboard_shows_low_stock_pantry_items(self):
        flour = Ingredient.objects.create(name="Plain flour", category=self._cat("Bakery"))
        sugar = Ingredient.objects.create(name="Sugar", category=self._cat("Baking"))
        PantryItem.objects.create(ingredient=flour, quantity=Decimal("0.25"), unit=Unit.KILOGRAM, low_stock_threshold=Decimal("0.50"))
        PantryItem.objects.create(ingredient=sugar, quantity=Decimal("2"), unit=Unit.KILOGRAM, low_stock_threshold=Decimal("0.50"))

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plain flour")
        self.assertNotContains(response, "Sugar")

    def test_shopping_list_subtracts_matching_pantry_stock(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("0.60"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("1000"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))
        item = shopping_list.items.get(ingredient_name="Tomatoes")

        self.assertEqual(item.quantity, Decimal("400.00"))
        self.assertEqual(item.unit, Unit.GRAM)
        self.assertEqual(item.pantry_used_quantity, Decimal("600.00"))
        self.assertEqual(item.pantry_used_unit, Unit.GRAM)
        self.assertIn("pantry used: 600 g", item.notes)
        self.assertEqual(PantryItem.objects.get(pk=PantryItem.objects.first().pk).quantity, Decimal("0.60"))

    def test_generate_shopping_list_refreshes_existing_week_list(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        recipe_ingredient = RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("100"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        response = self.client.post(
            reverse("generate_shopping_list"),
            {"supermarket": supermarket.pk, "week_start": "2026-06-01"},
        )
        shopping_list = ShoppingList.objects.get()
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))

        recipe_ingredient.quantity = Decimal("250")
        recipe_ingredient.save(update_fields=["quantity"])
        response = self.client.post(
            reverse("generate_shopping_list"),
            {"supermarket": supermarket.pk, "week_start": "2026-06-01"},
        )

        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        self.assertEqual(ShoppingList.objects.count(), 1)
        self.assertEqual(shopping_list.items.get(ingredient_name="Tomatoes").quantity, Decimal("250.00"))

    def test_restock_checked_shopping_items_updates_pantry(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        checked = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Dairy",
            ingredient_name="Milk",
            quantity=Decimal("2"),
            unit=Unit.LITRE,
            checked=True,
        )
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Bakery",
            ingredient_name="Bread",
            quantity=Decimal("1"),
            unit=Unit.ITEM,
            checked=False,
        )

        response = self.client.post(reverse("restock_shopping_list", args=[shopping_list.pk]))

        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        pantry_item = PantryItem.objects.get(ingredient__name=checked.ingredient_name)
        self.assertEqual(pantry_item.quantity, Decimal("2.00"))
        self.assertEqual(pantry_item.unit, Unit.LITRE)
        self.assertEqual(pantry_item.ingredient.category.name, "Dairy")
        self.assertFalse(PantryItem.objects.filter(ingredient__name="Bread").exists())

    def test_shopping_list_omits_items_fully_covered_by_pantry(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, entry.date, MealPlanEntry.objects.filter(pk=entry.pk))

        self.assertEqual(shopping_list.items.count(), 0)

    def test_shopping_list_does_not_subtract_incompatible_pantry_units(self):
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
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
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
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
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        pantry_item = PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("1"), unit=Unit.KILOGRAM)
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=tomatoes, quantity=Decimal("500"), unit=Unit.GRAM)
        entry = MealPlanEntry.objects.create(date=date(2026, 6, 1), meal_slot="dinner", recipe=recipe, servings=2)

        response = self.client.post(reverse("cook_planner_entry", args=[entry.pk]))
        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        pantry_item.refresh_from_db()
        entry.refresh_from_db()
        recipe.refresh_from_db()
        self.assertEqual(pantry_item.quantity, Decimal("0.50"))
        self.assertIsNotNone(entry.pantry_consumed_at)
        self.assertIsNotNone(recipe.last_cooked_at)
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
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
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

    def test_recipe_list_sorts_by_selected_option(self):
        small = Recipe.objects.create(title="Small salad", servings=1)
        large = Recipe.objects.create(title="Family pasta", servings=6)

        response = self.client.get(reverse("recipe_list") + "?sort=servings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["recipes"]), [small, large])
        self.assertEqual(response.context["sort"], "servings")

    def test_recipe_list_filters_by_favorites_and_missing_images(self):
        favorite = Recipe.objects.create(title="Favorite curry", servings=2, favorite=True)
        Recipe.objects.create(title="Plain pasta", servings=2)

        response = self.client.get(reverse("recipe_list") + "?filter=favorites")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["recipes"]), [favorite])
        self.assertEqual(response.context["selected_filter"], "favorites")

        response = self.client.get(reverse("recipe_list") + "?filter=missing_image")

        self.assertContains(response, "Favorite curry")
        self.assertContains(response, "Plain pasta")

    def test_recipe_detail_shows_metadata(self):
        recipe = Recipe.objects.create(
            title="Metadata soup",
            servings=2,
            prep_minutes=10,
            cook_minutes=30,
            source_url="https://example.com/soup",
            favorite=True,
        )

        response = self.client.get(reverse("recipe_detail", args=[recipe.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prep 10 min")
        self.assertContains(response, "Cook 30 min")
        self.assertContains(response, "https://example.com/soup")

    def test_planner_links_latest_shopping_list_for_selected_week(self):
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))

        response = self.client.get(reverse("planner") + "?week=2026-06-01")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        self.assertContains(response, "Open latest Tesco list")

    def test_parse_ingredient_line_duplicate_parenthetical(self):
        """Parenthetical text appearing multiple times only captures the first."""
        from .parser import parse_ingredient_line
        res = parse_ingredient_line("2 tbsp butter (melted) (salted)")
        self.assertEqual(res["name"], "butter (salted)")
        self.assertEqual(res["quantity"], "2")
        self.assertEqual(res["unit"], Unit.TABLESPOON)
        self.assertEqual(res["note"], "melted")

    def test_download_recipe_image_handles_timeout(self):
        """download_recipe_image returns empty string on network timeout."""
        from .parser import download_recipe_image
        with tempfile.TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                patch("recipes.parser.urllib.request.urlopen", side_effect=TimeoutError("timeout")),
            ):
                image_path = download_recipe_image("https://example.com/recipe.png")
            self.assertEqual(image_path, "")

    def test_recipe_detail_query_count(self):
        """recipe_detail has a fixed query count thanks to prefetch_related.

        Queries:
          1. Recipe lookup (pk)
          2. Tags prefetch
          3. Ingredients + ingredient prefetch
          4. Steps count (template calls .count() which bypasses prefetch cache)
          5. Steps prefetch (lazy, triggered on first .all() in template)
          6. Steps count (cook mode template section)
          7. Steps all (cook mode; Django re-queries due to intervening .count())
        """
        recipe = Recipe.objects.create(title="Test", servings=2)
        RecipeStep.objects.create(recipe=recipe, text="Step 1", order=0)
        RecipeStep.objects.create(recipe=recipe, text="Step 2", order=1)
        with self.assertNumQueries(7):
            response = self.client.get(reverse("recipe_detail", args=[recipe.pk]))
        self.assertEqual(response.status_code, 200)

    def test_parse_ingredient_line(self):
        from .parser import parse_ingredient_line
        
        # Test fractions
        res = parse_ingredient_line("1/2 cup flour, sifted")
        self.assertEqual(res["name"], "flour")
        self.assertEqual(res["quantity"], "0.5")
        self.assertEqual(res["unit"], Unit.CUP)
        self.assertEqual(res["note"], "sifted")
        
        # Test unicode fractions
        res2 = parse_ingredient_line("1\u00bd tsp salt")
        self.assertEqual(res2["name"], "salt")
        self.assertEqual(res2["quantity"], "1.5")
        self.assertEqual(res2["unit"], Unit.TEASPOON)

        res4 = parse_ingredient_line("\u00bd cup flour")
        self.assertEqual(res4["name"], "flour")
        self.assertEqual(res4["quantity"], "0.5")
        self.assertEqual(res4["unit"], Unit.CUP)

        res5 = parse_ingredient_line("\u00bc tsp spice")
        self.assertEqual(res5["name"], "spice")
        self.assertEqual(res5["quantity"], "0.25")
        self.assertEqual(res5["unit"], Unit.TEASPOON)
        
        # Test standard decimal & category lookup
        Ingredient.objects.create(name="chicken breast", category=self._cat("Meat"))
        res3 = parse_ingredient_line("500.50g chicken breast (skinless)")
        self.assertEqual(res3["name"], "chicken breast")
        self.assertEqual(res3["quantity"], "500.5")
        self.assertEqual(res3["unit"], Unit.GRAM)
        self.assertEqual(res3["note"], "skinless")
        self.assertEqual(res3["category"], "Meat")

    def test_parse_ingredient_line_alt_units(self):
        """Alternative metric/imperial patterns like '450g/1lb' are handled."""
        from .parser import parse_ingredient_line

        # BBC-style metric/imperial alternative
        res = parse_ingredient_line("450g/1lb Italian sausages")
        self.assertEqual(res["name"], "Italian sausages")
        self.assertEqual(res["quantity"], "450")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertEqual(res["note"], "")

        res = parse_ingredient_line("225g/8oz cheddar cheese")
        self.assertEqual(res["name"], "cheddar cheese")
        self.assertEqual(res["quantity"], "225")
        self.assertEqual(res["unit"], Unit.GRAM)

        # Slash with cup now maps to proper unit
        res = parse_ingredient_line("1 cup/250ml water")
        self.assertEqual(res["name"], "water")
        self.assertEqual(res["quantity"], "1")
        self.assertEqual(res["unit"], Unit.CUP)

        # No regression: standard unit without slash
        res = parse_ingredient_line("500.50g chicken breast (skinless)")
        self.assertEqual(res["name"], "chicken breast")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertEqual(res["quantity"], "500.5")

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
        self.assertEqual(res["ingredients"][0]["name"], "egg")
        self.assertEqual(res["ingredients"][0]["quantity"], "2")
        self.assertEqual(res["steps"][0]["text"], "Melt butter.")

    def test_parse_recipe_text_detects_title_and_servings(self):
        from .parser import parse_recipe_text
        raw_text = (
            "Lemon pasta\n"
            "Serves 3\n"
            "Ingredients\n"
            "200g spaghetti\n"
            "Instructions\n"
            "Boil pasta for 10 minutes.\n"
        )

        res = parse_recipe_text(raw_text)

        self.assertEqual(res["title"], "Lemon pasta")
        self.assertEqual(res["servings"], 3)
        self.assertEqual(res["ingredients"][0]["name"], "spaghetti")
        self.assertEqual(res["steps"][0]["duration_minutes"], 10)

    def test_recipe_import_saves_directly(self):
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
        with patch("recipes.views_recipes.parse_recipe_text", return_value=mock_data) as mock_parse:
            response = self.client.post(
                reverse("recipe_import"),
                {"raw_text": "2 large eggs\nCrack and fry."}
            )
            mock_parse.assert_called_once()
            self.assertEqual(response.status_code, 302)

        recipe = Recipe.objects.get(title="Mocked Egg")
        self.assertEqual(response["Location"], recipe.get_absolute_url())
        self.assertEqual(recipe.servings, 2)
        self.assertEqual(recipe.image.name, "recipes/imported_mock.jpg")
        self.assertEqual(recipe.ingredients.count(), 1)
        ing = recipe.ingredients.first()
        self.assertEqual(ing.ingredient.name, "egg")
        self.assertEqual(ing.note, "large")
        self.assertEqual(recipe.steps.count(), 1)
        self.assertEqual(recipe.steps.first().text, "Crack and fry.")
        self.assertEqual(list(recipe.tags.values_list("name", flat=True)), ["easy"])
        self.assertNotIn("imported_recipe", self.client.session)

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
        MealPlanEntry.objects.create(date=source_date, meal_slot="dinner", recipe=recipe, servings=4, note="Use leftovers")

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
        self.assertEqual(entries[key].note, "Use leftovers")

        # Verify that no entries were actually saved in the DB for the target week yet
        self.assertFalse(MealPlanEntry.objects.filter(date=target_date).exists())

    def test_planner_saves_meal_notes(self):
        recipe = Recipe.objects.create(title="Tacos", servings=4)

        response = self.client.post(
            reverse("planner") + "?week=2026-06-01",
            {
                "recipe_2026-06-01_dinner": str(recipe.pk),
                "servings_2026-06-01_dinner": "4",
                "note_2026-06-01_dinner": "Make extra salsa",
            },
        )

        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        entry = MealPlanEntry.objects.get(date=date(2026, 6, 1), meal_slot="dinner")
        self.assertEqual(entry.note, "Make extra salsa")

    def test_planner_saves_visible_grid_as_template(self):
        recipe = Recipe.objects.create(title="Tacos", servings=4)

        response = self.client.post(
            reverse("planner") + "?week=2026-06-01",
            {
                "planner_action": "save_template",
                "template_name": "Family favourites",
                "recipe_2026-06-01_dinner": str(recipe.pk),
                "servings_2026-06-01_dinner": "3",
                "note_2026-06-01_dinner": "Make extra salsa",
            },
        )

        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        self.assertFalse(MealPlanEntry.objects.exists())
        template = MealPlanTemplate.objects.get(name="Family favourites")
        template_entry = template.entries.get()
        self.assertEqual(template_entry.day_offset, 0)
        self.assertEqual(template_entry.meal_slot, "dinner")
        self.assertEqual(template_entry.recipe, recipe)
        self.assertEqual(template_entry.servings, 3)
        self.assertEqual(template_entry.note, "Make extra salsa")

    def test_planner_template_preview_does_not_create_entries(self):
        recipe = Recipe.objects.create(title="Tacos", servings=4)
        template = MealPlanTemplate.objects.create(name="Family favourites")
        MealPlanTemplateEntry.objects.create(
            template=template,
            day_offset=2,
            meal_slot="lunch",
            recipe=recipe,
            servings=2,
            note="Use leftovers",
        )

        response = self.client.get(reverse("planner") + f"?week=2026-06-08&template={template.pk}")

        self.assertEqual(response.status_code, 200)
        entries = response.context["entries"]
        key = "2026-06-10_lunch"
        self.assertIn(key, entries)
        self.assertEqual(entries[key].recipe_id, recipe.pk)
        self.assertEqual(entries[key].servings, 2)
        self.assertEqual(entries[key].note, "Use leftovers")
        self.assertTrue(response.context["template_preview"])
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_planner_saves_template_preview_as_meal_plan(self):
        recipe = Recipe.objects.create(title="Tacos", servings=4)

        response = self.client.post(
            reverse("planner") + "?week=2026-06-08",
            {
                "planner_action": "save_plan",
                "recipe_2026-06-10_lunch": str(recipe.pk),
                "servings_2026-06-10_lunch": "2",
                "note_2026-06-10_lunch": "Use leftovers",
            },
        )

        self.assertRedirects(response, reverse("planner") + "?week=2026-06-08")
        entry = MealPlanEntry.objects.get(date=date(2026, 6, 10), meal_slot="lunch")
        self.assertEqual(entry.recipe, recipe)
        self.assertEqual(entry.servings, 2)
        self.assertEqual(entry.note, "Use leftovers")

    def test_planner_saving_existing_template_name_replaces_entries(self):
        tacos = Recipe.objects.create(title="Tacos", servings=4)
        pasta = Recipe.objects.create(title="Pasta", servings=4)
        template = MealPlanTemplate.objects.create(name="Family favourites")
        MealPlanTemplateEntry.objects.create(
            template=template,
            day_offset=0,
            meal_slot="dinner",
            recipe=tacos,
            servings=4,
        )

        response = self.client.post(
            reverse("planner") + "?week=2026-06-01",
            {
                "planner_action": "save_template",
                "template_name": "family favourites",
                "recipe_2026-06-02_lunch": str(pasta.pk),
                "servings_2026-06-02_lunch": "5",
            },
        )

        self.assertRedirects(response, reverse("planner") + "?week=2026-06-01")
        self.assertEqual(MealPlanTemplate.objects.count(), 1)
        template.refresh_from_db()
        self.assertEqual(template.name, "family favourites")
        template_entry = template.entries.get()
        self.assertEqual(template_entry.day_offset, 1)
        self.assertEqual(template_entry.meal_slot, "lunch")
        self.assertEqual(template_entry.recipe, pasta)
        self.assertEqual(template_entry.servings, 5)

    def test_planner_template_delete(self):
        template = MealPlanTemplate.objects.create(name="Family favourites")

        response = self.client.post(reverse("delete_meal_plan_template", args=[template.pk]))

        self.assertRedirects(response, reverse("planner"))
        self.assertFalse(MealPlanTemplate.objects.exists())

    def test_custom_item_checked_state_preserved_after_regeneration(self):
        """Custom shopping items retain their checked state after list regeneration."""
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        recipe = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=tomatoes, quantity=Decimal("100"), unit=Unit.GRAM,
        )
        MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")
        SupermarketSection.objects.create(supermarket=supermarket, name="Fruit & veg", order=0)
        shopping_list = build_shopping_list(supermarket, date(2026, 6, 1), MealPlanEntry.objects.all())

        # Add a custom checked item
        custom = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            section_name="Dairy",
            section_order=1,
            ingredient_name="Milk",
            quantity=Decimal("2"),
            unit=Unit.LITRE,
            checked=True,
            is_custom=True,
        )

        # Regenerate
        response = self.client.post(reverse("regenerate_shopping_list", args=[shopping_list.pk]))
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))

        custom.refresh_from_db()
        self.assertTrue(custom.is_custom)
        self.assertTrue(custom.checked)

    def test_shopping_item_zero_quantity_handling(self):
        """Adding a shopping item with zero or negative quantity defaults to 1."""
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))

        # Zero quantity
        response = self.client.post(
            reverse("add_shopping_item", args=[shopping_list.pk]),
            {"ingredient_name": "Milk", "quantity": "0", "unit": Unit.LITRE, "section_name": "Dairy"},
        )
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        item = ShoppingListItem.objects.get(shopping_list=shopping_list, ingredient_name="Milk")
        self.assertEqual(item.quantity, Decimal("1"))

        # Negative quantity
        response = self.client.post(
            reverse("add_shopping_item", args=[shopping_list.pk]),
            {"ingredient_name": "Eggs", "quantity": "-5", "unit": Unit.ITEM, "section_name": "Dairy"},
        )
        item2 = ShoppingListItem.objects.get(shopping_list=shopping_list, ingredient_name="Eggs")
        self.assertEqual(item2.quantity, Decimal("1"))

    def test_edit_shopping_item_rejects_invalid_quantity(self):
        """Editing a shopping item with invalid quantity shows error and does not update."""
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list, section_name="Bakery",
            ingredient_name="Bread", quantity=Decimal("1"), unit=Unit.ITEM,
        )

        response = self.client.post(
            reverse("edit_shopping_item", args=[item.pk]),
            {"ingredient_name": "Bread", "quantity": "abc", "unit": Unit.ITEM, "section_name": "Bakery"},
        )
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("1"))  # unchanged

    def test_restock_preserves_category_if_already_set(self):
        """Restocking does not overwrite an ingredient's existing category."""
        supermarket = Supermarket.objects.create(name="Tesco")
        shopping_list = ShoppingList.objects.create(supermarket=supermarket, week_start=date(2026, 6, 1))
        ShoppingListItem.objects.create(
            shopping_list=shopping_list, section_name="Drinks",
            ingredient_name="Milk", quantity=Decimal("1"), unit=Unit.LITRE, checked=True,
        )

        # Ingredient already has a category
        milk = Ingredient.objects.create(name="Milk", category=self._cat("Dairy"))

        response = self.client.post(reverse("restock_shopping_list", args=[shopping_list.pk]))
        self.assertRedirects(response, reverse("shopping_list_detail", args=[shopping_list.pk]))
        milk.refresh_from_db()
        self.assertEqual(milk.category.name, "Dairy")  # preserved, not overwritten to "Drinks"

    def test_unit_bucket_graceful_fallback(self):
        """unit_bucket returns ITEM group for unknown units instead of crashing."""
        result = unit_bucket("unknown_unit_xyz")
        self.assertEqual(result, ("item", Decimal("1"), Unit.ITEM))

    def test_multi_recipe_pantry_deduction(self):
        """Two recipes sharing the same ingredient correctly split limited pantry stock."""
        tomatoes = Ingredient.objects.create(name="Tomatoes", category=self._cat("Fruit & veg"))
        PantryItem.objects.create(ingredient=tomatoes, quantity=Decimal("0.50"), unit=Unit.KILOGRAM)
        recipe_a = Recipe.objects.create(title="Pasta", servings=2)
        RecipeIngredient.objects.create(recipe=recipe_a, ingredient=tomatoes, quantity=Decimal("300"), unit=Unit.GRAM)
        recipe_b = Recipe.objects.create(title="Pizza", servings=2)
        RecipeIngredient.objects.create(recipe=recipe_b, ingredient=tomatoes, quantity=Decimal("300"), unit=Unit.GRAM)

        MealPlanEntry.objects.create(date="2026-06-01", meal_slot="dinner", recipe=recipe_a, servings=2)
        MealPlanEntry.objects.create(date="2026-06-02", meal_slot="dinner", recipe=recipe_b, servings=2)
        supermarket = Supermarket.objects.create(name="Tesco")

        shopping_list = build_shopping_list(supermarket, date(2026, 6, 1), MealPlanEntry.objects.all())

        # Pantry has 500g, total need is 600g → only 100g should need buying
        item = shopping_list.items.get(ingredient_name="Tomatoes")
        self.assertEqual(item.quantity, Decimal("100.00"))
        self.assertEqual(item.unit, Unit.GRAM)
        self.assertEqual(item.pantry_used_quantity, Decimal("500.00"))

    def test_recipe_detail_query_count(self):
        """Recipe detail page uses prefetched steps to avoid N+1 queries."""
        AppSetting.current()
        recipe = Recipe.objects.create(title="Multi-step recipe", servings=2)
        RecipeStep.objects.create(recipe=recipe, text="Step one", order=0)
        RecipeStep.objects.create(recipe=recipe, text="Step two", order=1)
        RecipeStep.objects.create(recipe=recipe, text="Step three", order=2)

        with self.assertNumQueries(5):
            # 1. Recipe + tags + ingredients + steps (all prefetched)
            # 2. Ingredient names for select_related
            # 3. Session lookup
            # 4. AppSetting accent lookup (context processor)
            response = self.client.get(reverse("recipe_detail", args=[recipe.pk]))

        self.assertEqual(response.status_code, 200)

    # -- smart quantity display ----------------------------------------------

    def test_smart_quantity_display_kg(self):
        """1000 g -> '1 kg', 1500 g -> '1.5 kg', 500 g -> '500 g'."""
        from .templatetags.recipe_extras import smart_quantity_display

        item = Mock(quantity=1000, unit="g")
        self.assertEqual(smart_quantity_display(item), "1 kg")

        item = Mock(quantity=1500, unit="g")
        self.assertEqual(smart_quantity_display(item), "1.5 kg")

        item = Mock(quantity=500, unit="g")
        self.assertIn("500", smart_quantity_display(item))
        self.assertIn("g", smart_quantity_display(item))

    def test_smart_quantity_display_l(self):
        """1000 ml -> '1 L', 2500 ml -> '2.5 L'."""
        from .templatetags.recipe_extras import smart_quantity_display

        item = Mock(quantity=1000, unit="ml")
        self.assertEqual(smart_quantity_display(item), "1 L")

        item = Mock(quantity=2500, unit="ml")
        self.assertEqual(smart_quantity_display(item), "2.5 L")

    def test_smart_quantity_display_item(self):
        """'item' unit hides the unit label."""
        from .templatetags.recipe_extras import smart_quantity_display

        item = Mock(quantity=3, unit="item")
        self.assertEqual(smart_quantity_display(item), "3")

    def test_smart_quantity_display_other_units(self):
        """Non-g/ml units display with their original unit label."""
        from .templatetags.recipe_extras import smart_quantity_display

        item = Mock(quantity=2, unit="tbsp")
        result = smart_quantity_display(item)
        self.assertIn("2", result)
        self.assertIn("tbsp", result)


class MockScraper:
    """Simulates a recipe-scrapers scraper object with configurable return values."""

    def __init__(self, **overrides):
        self._title = overrides.get("title", "Test Recipe")
        self._yields = overrides.get("yields", 4)
        self._instructions = overrides.get("instructions", ["Step one", "Step two"])
        self._ingredients = overrides.get("ingredients", ["200g spaghetti", "2 tbsp olive oil"])
        self._keywords = overrides.get("keywords", ["easy", "pasta"])
        self._category = overrides.get("category", "Dinner")
        self._image = overrides.get("image", None)

    def title(self):
        return self._title
    def yields(self):
        return self._yields
    def instructions(self):
        return self._instructions
    def ingredients(self):
        return self._ingredients
    def keywords(self):
        return self._keywords
    def category(self):
        return self._category
    def image(self):
        return self._image


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RecipeParseRecipeUrlTests(TestCase):
    """Tests for parse_recipe_url with mocked scrapers."""

    def test_instructions_list_of_strings(self):
        """Instructions as a list of strings is the most common scraper output."""
        scraper = MockScraper(
            instructions=["Boil water.", "Add pasta.", "Cook for 10 minutes."],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/pasta")
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["steps"][0]["text"], "Boil water.")
        self.assertEqual(result["steps"][1]["text"], "Add pasta.")
        self.assertEqual(result["steps"][2]["duration_minutes"], 10)

    def test_instructions_list_of_dicts(self):
        """Some scrapers return instructions as a list of dicts with 'text' key."""
        scraper = MockScraper(
            instructions=[
                {"text": "Preheat oven to 180C."},
                {"text": "Bake for 30 minutes."},
            ],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/bake")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["steps"][0]["text"], "Preheat oven to 180C.")
        self.assertEqual(result["steps"][1]["duration_minutes"], 30)

    def test_instructions_single_multiline_string(self):
        """Fallback: instructions returned as a single string with newlines."""
        scraper = MockScraper(
            instructions="Mix dry ingredients.\nAdd wet ingredients.\nBake.",
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/cake")
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["steps"][0]["text"], "Mix dry ingredients.")

    def test_instructions_empty_string(self):
        """Empty instructions string produces no steps."""
        scraper = MockScraper(instructions="")
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/empty")
        self.assertEqual(result["steps"], [])

    def test_instructions_none(self):
        """None instructions produces no steps."""
        scraper = MockScraper(instructions=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/none")
        self.assertEqual(result["steps"], [])

    def test_yields_none_defaults_to_four(self):
        """When yields is None, servings should default to 4."""
        scraper = MockScraper(yields=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/soup")
        self.assertEqual(result["servings"], 4)

    def test_yields_zero_string_defaults_to_one(self):
        """When yields is '0', servings should be 1 (minimum)."""
        scraper = MockScraper(yields="0")
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/soup")
        self.assertEqual(result["servings"], 1)

    def test_keywords_none_yields_only_category_tag(self):
        """When keywords is None, only the category tag is included."""
        scraper = MockScraper(keywords=None, category="Dinner")
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/soup")
        self.assertEqual(result["tags_list"], ["dinner"])

    def test_keywords_as_comma_string(self):
        """Some scrapers return keywords as a comma-separated string."""
        scraper = MockScraper(keywords="easy, quick, pasta", category=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/soup")
        self.assertEqual(result["tags_list"], ["easy", "pasta", "quick"])

    def test_keywords_empty_list_without_category(self):
        """Empty list of keywords and no category produces no tags."""
        scraper = MockScraper(keywords=[], category=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/soup")
        self.assertEqual(result["tags_list"], [])

    def test_category_as_string_adds_to_tags(self):
        """Category string should be included in tags_list."""
        scraper = MockScraper(category="Main course")
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/main")
        self.assertIn("main course", result["tags_list"])

    def test_category_none(self):
        """None category should not crash and not add to tags."""
        scraper = MockScraper(category=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/main")
        self.assertEqual(result["tags_list"], ["easy", "pasta"])

    def test_tags_limited_to_five(self):
        """tags_list should be capped at 5 sorted unique tags."""
        scraper = MockScraper(
            keywords=["a", "b", "c", "d", "e", "f", "g"],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/tags")
        self.assertEqual(len(result["tags_list"]), 5)

    def test_image_none_still_succeeds(self):
        """When image() returns None, the parser should still succeed."""
        scraper = MockScraper(image=None)
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/noimage")
        self.assertEqual(result["image_path"], "")

    def test_source_url_preserved_in_result(self):
        """The source_url in the result should match the input URL."""
        scraper = MockScraper()
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/my-recipe")
        self.assertEqual(result["source_url"], "https://example.com/my-recipe")

    def test_ingredients_parsed_into_structured_format(self):
        """Ingredient lines should be parsed into structured dicts."""
        scraper = MockScraper(
            ingredients=["1 cup flour", "2 tbsp butter, melted", "3 eggs"],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/bake")
        self.assertEqual(len(result["ingredients"]), 3)
        self.assertEqual(result["ingredients"][0]["name"], "flour")
        self.assertEqual(result["ingredients"][0]["unit"], Unit.CUP)
        self.assertEqual(result["ingredients"][1]["name"], "butter")
        self.assertEqual(result["ingredients"][1]["note"], "melted")

    def test_instructions_list_with_empty_dicts(self):
        """List of dicts where some have empty text should skip those."""
        scraper = MockScraper(
            instructions=[
                {"text": ""},
                {"text": "Real step here."},
            ],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/step")
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["text"], "Real step here.")

    def test_instructions_list_with_non_dict_items(self):
        """List of mixed types: non-dict items are converted to string."""
        scraper = MockScraper(
            instructions=["Step one", {"text": "Step two"}],
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/mixed")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["steps"][0]["text"], "Step one")
        self.assertEqual(result["steps"][1]["text"], "Step two")

    def test_ingredients_empty_list(self):
        """Empty ingredients list produces no ingredients."""
        scraper = MockScraper(ingredients=[])
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/empty")
        self.assertEqual(result["ingredients"], [])

    def test_keywords_removes_duplicates_and_sorts(self):
        """Duplicate keywords across keywords() and category() should be deduplicated."""
        scraper = MockScraper(
            keywords=["dinner", "quick", "quick"],
            category="Dinner",
        )
        with patch("recipes.parser.scrape_me", return_value=scraper):
            result = parse_recipe_url("https://example.com/dupes")
        self.assertEqual(result["tags_list"], ["dinner", "quick"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RecipeScraperMinutesTests(TestCase):
    """Tests for scraper_minutes helper."""

    class MockScraper:
        pass

    def test_method_missing(self):
        """When the method does not exist on scraper, return None."""
        scraper = self.MockScraper()
        result = scraper_minutes(scraper, "nonexistent_method")
        self.assertIsNone(result)

    def test_returns_none(self):
        """When method returns None, return None."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: None
        result = scraper_minutes(scraper, "prep_time")
        self.assertIsNone(result)

    def test_returns_empty_string(self):
        """When method returns empty string, return None."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: ""
        result = scraper_minutes(scraper, "prep_time")
        self.assertIsNone(result)

    def test_returns_non_numeric_string(self):
        """When method returns non-numeric string, extract digits."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: "about 30 minutes"
        result = scraper_minutes(scraper, "prep_time")
        self.assertEqual(result, 30)

    def test_returns_valid_int(self):
        """When method returns valid int, return it."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: 30
        result = scraper_minutes(scraper, "prep_time")
        self.assertEqual(result, 30)

    def test_returns_valid_string_number(self):
        """When method returns string number, return int."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: "45"
        result = scraper_minutes(scraper, "prep_time")
        self.assertEqual(result, 45)

    def test_returns_zero(self):
        """When method returns 0, return None."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: 0
        result = scraper_minutes(scraper, "prep_time")
        self.assertIsNone(result)

    def test_returns_negative(self):
        """When method returns negative, clamp to 1."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: -5
        result = scraper_minutes(scraper, "prep_time")
        self.assertEqual(result, 1)

    def test_method_raises_exception(self):
        """When method raises exception, return None."""
        scraper = self.MockScraper()
        def raise_error():
            raise ValueError("scraper error")
        scraper.prep_time = raise_error
        result = scraper_minutes(scraper, "prep_time")
        self.assertIsNone(result)

    def test_returns_string_with_no_digits(self):
        """When method returns string with no digits, return None."""
        scraper = self.MockScraper()
        scraper.prep_time = lambda: "unknown"
        result = scraper_minutes(scraper, "prep_time")
        self.assertIsNone(result)


class RecipeParseServingsTests(TestCase):
    """Tests for parse_servings helper."""

    def test_none(self):
        """None input defaults to 4."""
        self.assertEqual(parse_servings(None), 4)

    def test_valid_int(self):
        """Int input is returned as-is."""
        self.assertEqual(parse_servings(4), 4)

    def test_float(self):
        """Float input is truncated to int."""
        self.assertEqual(parse_servings(4.5), 4)

    def test_string_with_number(self):
        """String with number extracts the first number."""
        self.assertEqual(parse_servings("Serves 4-6"), 4)

    def test_string_no_number(self):
        """String with no number defaults to 4."""
        self.assertEqual(parse_servings("unknown"), 4)

    def test_zero(self):
        """Zero input clamps to 1."""
        self.assertEqual(parse_servings(0), 1)

    def test_negative(self):
        """Negative input clamps to 1."""
        self.assertEqual(parse_servings(-3), 1)

    def test_string_zero(self):
        """String '0' clamps to 1."""
        self.assertEqual(parse_servings("0"), 1)

    def test_empty_string(self):
        """Empty string defaults to 4."""
        self.assertEqual(parse_servings(""), 4)

    def test_large_number(self):
        """Large number is preserved."""
        self.assertEqual(parse_servings(100), 100)


class RecipeExtractStepDurationTests(TestCase):
    """Tests for extract_step_duration helper."""

    def test_minutes_only(self):
        """'Bake for 45 minutes' returns 45."""
        self.assertEqual(extract_step_duration("Bake for 45 minutes at 180C"), 45)

    def test_hours_only(self):
        """'Simmer for 1 hour' returns 60."""
        self.assertEqual(extract_step_duration("Simmer for 1 hour"), 60)

    def test_hours_and_minutes(self):
        """'Boil for 1 hr and 15 mins' returns 75."""
        self.assertEqual(extract_step_duration("Boil for 1 hr and 15 mins"), 75)

    def test_hr_abbreviation(self):
        """'Cook for 2 hrs' returns 120."""
        self.assertEqual(extract_step_duration("Cook for 2 hrs"), 120)

    def test_min_abbreviation(self):
        """'Rest for 10 min' returns 10."""
        self.assertEqual(extract_step_duration("Rest for 10 min"), 10)

    def test_no_time_mention(self):
        """No time mention returns None."""
        self.assertIsNone(extract_step_duration("Mix ingredients together"))

    def test_empty_string(self):
        """Empty string returns None."""
        self.assertIsNone(extract_step_duration(""))

    def test_none_input(self):
        """None input returns None."""
        self.assertIsNone(extract_step_duration(None))

    def test_hours_then_minutes_without_conjunction(self):
        """'3 hours 20 minutes' returns 200."""
        self.assertEqual(extract_step_duration("Rise for 3 hours 20 minutes"), 200)

    def test_time_in_middle_of_sentence(self):
        """Time mention in middle of sentence is still detected."""
        self.assertEqual(
            extract_step_duration("First, simmer for 30 minutes, then add salt."),
            30,
        )

    def test_hour_minutes_plural(self):
        """'2 hours and 30 minutes' returns 150."""
        self.assertEqual(extract_step_duration("Steam for 2 hours and 30 minutes"), 150)


class RecipeParseIngredientLineEdgeCases(TestCase):
    """Edge cases for parse_ingredient_line."""

    def test_empty_line(self):
        """Empty line returns None."""
        self.assertIsNone(parse_ingredient_line(""))

    def test_whitespace_line(self):
        """Whitespace-only line returns None."""
        self.assertIsNone(parse_ingredient_line("   "))

    def test_default_quantity(self):
        """Ingredient with no quantity defaults to 1.0."""
        res = parse_ingredient_line("onion")
        self.assertEqual(res["name"], "onion")
        self.assertEqual(res["quantity"], "1")
        self.assertEqual(res["unit"], Unit.ITEM)

    def test_mixed_fraction_with_hyphen(self):
        """Mixed fraction like '1 1/2 cups sugar' works."""
        res = parse_ingredient_line("1 1/2 cups sugar")
        self.assertEqual(res["name"], "sugar")
        self.assertEqual(res["quantity"], "1.5")
        self.assertEqual(res["unit"], Unit.CUP)

    def test_of_prefix_after_unit(self):
        """'1 cup of flour' strips 'of' prefix from name."""
        res = parse_ingredient_line("1 cup of flour")
        self.assertEqual(res["name"], "flour")
        self.assertEqual(res["unit"], Unit.CUP)

    def test_x_prefix(self):
        """'1 x 2 litre carton milk' extracts quantity and unit after 'x'."""
        res = parse_ingredient_line("1 x 2 litre carton milk")
        self.assertEqual(res["quantity"], "2")
        self.assertEqual(res["unit"], Unit.LITRE)
        self.assertEqual(res["name"], "carton milk")

    def test_dash_prefix(self):
        """'-' prefix after quantity is stripped."""
        res = parse_ingredient_line("1 - onion")
        self.assertEqual(res["name"], "onion")
        self.assertEqual(res["quantity"], "1")

    def test_comma_note(self):
        """Text after comma becomes note."""
        res = parse_ingredient_line("2 tbsp butter, melted")
        self.assertEqual(res["name"], "butter")
        self.assertEqual(res["note"], "melted")

    def test_paren_and_comma_note(self):
        """Both parenthetical and comma notes combine."""
        res = parse_ingredient_line("2 tbsp butter (unsalted), melted")
        self.assertEqual(res["name"], "butter")
        self.assertEqual(res["note"], "unsalted, melted")

    def test_non_standard_unit_in_parens(self):
        """Non-standard unit like 'canned' does not match 'can' mapping because it's the full word 'canned'."""
        res = parse_ingredient_line("400g canned tomatoes")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertEqual(res["quantity"], "400")
        self.assertEqual(res["name"], "canned tomatoes")

    def test_item_unit_default(self):
        """Plain ingredient with no unit defaults to ITEM."""
        res = parse_ingredient_line("3 eggs")
        self.assertEqual(res["name"], "egg")
        self.assertEqual(res["quantity"], "3")
        self.assertEqual(res["unit"], Unit.ITEM)

    def test_unit_mapping_with_period(self):
        """Unit abbreviations with periods like 'tsp.' are recognized."""
        res = parse_ingredient_line("1 tsp. salt")
        self.assertEqual(res["name"], "salt")
        self.assertEqual(res["unit"], Unit.TEASPOON)

    def test_unit_mapping_with_trailing_period(self):
        """Unit abbreviations with trailing period are cleaned."""
        res = parse_ingredient_line("1 tbsp. olive oil")
        self.assertEqual(res["name"], "olive oil")
        self.assertEqual(res["unit"], Unit.TABLESPOON)

    def test_slash_metric_imperial(self):
        """Metric/imperial alternative like '450g/1lb' is parsed."""
        res = parse_ingredient_line("450g/1lb Italian sausages")
        self.assertEqual(res["name"], "Italian sausages")
        self.assertEqual(res["quantity"], "450")
        self.assertEqual(res["unit"], Unit.GRAM)

    def test_non_standard_unit_slash(self):
        """Slash unit with cup now maps to proper unit."""
        res = parse_ingredient_line("1 cup/250ml water")
        self.assertEqual(res["name"], "water")
        self.assertEqual(res["quantity"], "1")
        self.assertEqual(res["unit"], Unit.CUP)

    def test_very_long_name(self):
        """Long ingredient names are preserved."""
        res = parse_ingredient_line("1 tbsp freshly squeezed lemon juice")
        self.assertEqual(res["name"], "freshly squeezed lemon juice")
        self.assertEqual(res["unit"], Unit.TABLESPOON)

    def test_decimal_quantity(self):
        """Decimal quantities are parsed correctly."""
        res = parse_ingredient_line("0.5 kg chicken")
        self.assertEqual(res["name"], "chicken")
        self.assertEqual(res["quantity"], "0.5")
        self.assertEqual(res["unit"], Unit.KILOGRAM)

    def test_unicode_fraction_alone(self):
        """Unicode fraction alone is parsed."""
        res = parse_ingredient_line("\u00bd lemon")
        self.assertEqual(res["name"], "lemon")
        self.assertEqual(res["quantity"], "0.5")

    def test_mixed_unicode_fraction(self):
        """Mixed number with unicode fraction is parsed."""
        res = parse_ingredient_line("1\u00bd cups milk")
        self.assertEqual(res["name"], "milk")
        self.assertEqual(res["quantity"], "1.5")
        self.assertEqual(res["unit"], Unit.CUP)

    def test_serving_instruction_to_taste(self):
        """'Salt and pepper to taste' should be filtered out."""
        res = parse_ingredient_line("Salt and pepper to taste")
        self.assertIsNone(res)

    def test_serving_instruction_for_garnish(self):
        """'Fresh basil for garnish' should be filtered out."""
        res = parse_ingredient_line("Fresh basil for garnish")
        self.assertIsNone(res)

    def test_serving_instruction_to_serve(self):
        """'caster sugar to serve (optional)' should be filtered out."""
        res = parse_ingredient_line("caster sugar to serve (optional)")
        self.assertIsNone(res)

    def test_serving_instruction_for_serving(self):
        """'Parmesan cheese for serving' should be filtered out."""
        res = parse_ingredient_line("Parmesan cheese for serving")
        self.assertIsNone(res)

    def test_serving_instruction_comma_to_serve(self):
        """'Spaghetti, to serve' should be filtered out (note check)."""
        res = parse_ingredient_line("Spaghetti, to serve")
        self.assertIsNone(res)

    def test_serving_instruction_for_garnish_colon(self):
        """'For garnish: fresh herbs' should be filtered out."""
        res = parse_ingredient_line("For garnish: fresh herbs")
        self.assertIsNone(res)

    def test_real_ingredient_salt_and_pepper(self):
        """'salt and pepper' (without 'to taste') should NOT be filtered."""
        res = parse_ingredient_line("salt and pepper")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "salt and pepper")

    def test_real_ingredient_basil(self):
        """'fresh basil' (without 'for garnish') should NOT be filtered."""
        res = parse_ingredient_line("fresh basil")
        self.assertIsNotNone(res)
        self.assertIn("basil", res["name"])

    def test_real_ingredient_basil_leaves_comma_garnish(self):
        """'fresh basil leaves, for garnish' should be filtered (note check)."""
        res = parse_ingredient_line("fresh basil leaves, for garnish")
        self.assertIsNone(res)

    def test_real_ingredient_garnish_with(self):
        """'garnish with fresh herbs' should be filtered out."""
        res = parse_ingredient_line("garnish with fresh herbs")
        self.assertIsNone(res)

    def test_article_a_with_pinch(self):
        """'a pinch of salt' should detect pinch as unit."""
        res = parse_ingredient_line("a pinch of salt")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "salt")
        self.assertEqual(res["unit"], Unit.PINCH)

    def test_article_a_with_bunch(self):
        """'a bunch of parsley' should detect bunch as unit."""
        res = parse_ingredient_line("a bunch of parsley")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "parsley")
        self.assertEqual(res["unit"], Unit.BUNCH)

    def test_article_a_before_unit(self):
        """'a tbsp butter' should detect tbsp as unit."""
        res = parse_ingredient_line("a tbsp butter")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "butter")
        self.assertEqual(res["unit"], Unit.TABLESPOON)

    def test_article_an_no_unit(self):
        """'an onion' should not crash and default to item."""
        res = parse_ingredient_line("an onion")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "onion")
        self.assertEqual(res["unit"], Unit.ITEM)

    def test_article_an_with_eggplant(self):
        """'an eggplant' should not crash."""
        res = parse_ingredient_line("an eggplant")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "eggplant")
        self.assertEqual(res["unit"], Unit.ITEM)

    def test_x_prefix_with_weight(self):
        """'1 x 400g can tomatoes' should extract 400g."""
        res = parse_ingredient_line("1 x 400g can chopped tomatoes")
        self.assertIsNotNone(res)
        self.assertEqual(res["quantity"], "400")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertNotIn("400g", res["name"])

    def test_x_prefix_with_volume(self):
        """'1 x 2 litre carton milk' should extract 2 litre."""
        res = parse_ingredient_line("1 x 2 litre carton milk")
        self.assertIsNotNone(res)
        self.assertEqual(res["quantity"], "2")
        self.assertEqual(res["unit"], Unit.LITRE)
        self.assertEqual(res["name"], "carton milk")

    def test_x_prefix_no_quantity(self):
        """'1 x egg' should not override quantity."""
        res = parse_ingredient_line("1 x egg")
        self.assertIsNotNone(res)
        self.assertEqual(res["quantity"], "1")
        self.assertEqual(res["unit"], Unit.ITEM)
        self.assertEqual(res["name"], "egg")

    def test_x_prefix_multiple_cans(self):
        """'2 x 400g can tomatoes' re-extracts inner qty with unit."""
        res = parse_ingredient_line("2 x 400g can chopped tomatoes")
        self.assertIsNotNone(res)
        self.assertEqual(res["quantity"], "400")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertIn("can chopped tomatoes", res["name"])

    def test_x_prefix_pot_yogurt(self):
        """'1 x 150g pot natural yogurt' should extract 150g."""
        res = parse_ingredient_line("1 x 150g pot natural yogurt")
        self.assertIsNotNone(res)
        self.assertEqual(res["quantity"], "150")
        self.assertEqual(res["unit"], Unit.GRAM)
        self.assertNotIn("150g", res["name"])

    def test_trailing_instruction_plus_for_frying(self):
        """'1 tbsp oil plus extra for frying' should move trailing text to note."""
        res = parse_ingredient_line("1 tbsp sunflower oil plus a little extra for frying")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "sunflower oil")
        self.assertIn("frying", res["note"])

    def test_trailing_instruction_for_cooking(self):
        """'200g pasta for cooking' should move 'for cooking' to note."""
        res = parse_ingredient_line("200g pasta for cooking")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "pasta")
        self.assertIn("cooking", res["note"])

    def test_trailing_instruction_no_match_stays_in_name(self):
        """'extra virgin olive oil' should NOT be split (no instruction word)."""
        res = parse_ingredient_line("extra virgin olive oil")
        self.assertIsNotNone(res)
        self.assertIn("olive", res["name"])
        self.assertEqual(res["note"], "")


class RecipeParserViewIntegrationTests(TestCase):
    """Integration tests for the recipe import view's error handling."""

    def test_import_view_invalid_url_returns_error_message(self):
        """When scrape_me raises, the view should show an error message."""
        with patch("recipes.views_recipes.parse_recipe_url", side_effect=ValueError("Invalid recipe URL")):
            response = self.client.post(
                reverse("recipe_import"),
                {"url": "https://invalid.com/recipe"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid recipe URL")

    def test_import_view_http_error_shows_message(self):
        """HTTP errors from scraping are shown as user-facing messages."""
        with patch("recipes.views_recipes.parse_recipe_url", side_effect=ConnectionError("Connection refused")):
            response = self.client.post(
                reverse("recipe_import"),
                {"url": "https://down.site/recipe"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Could not connect to the website")

    def test_import_view_complex_exception_shows_message(self):
        """Any exception during import shows the message."""
        with patch("recipes.views_recipes.parse_recipe_url", side_effect=RuntimeError("Unexpected scraper crash")):
            response = self.client.post(
                reverse("recipe_import"),
                {"url": "https://example.com/crash"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Something went wrong during import")

    def test_import_view_missing_url_and_text(self):
        """When both URL and text are empty, show an error."""
        response = self.client.post(
            reverse("recipe_import"),
            {"url": "", "raw_text": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "provide either a URL or raw text")

    def test_import_duplicate_title_warning(self):
        """Importing a recipe with a title that matches an existing recipe shows a warning."""
        Recipe.objects.create(title="Existing Recipe", servings=2)
        mock_data = {
            "title": "Existing Recipe",
            "servings": 4,
            "steps": [{"text": "Step 1", "duration_minutes": None}],
            "ingredients": [{"name": "flour", "quantity": "1.00", "unit": "item", "note": "", "category": ""}],
            "tags_list": [],
            "image_path": "",
        }
        with patch("recipes.views_recipes.parse_recipe_text", return_value=mock_data):
            response = self.client.post(
                reverse("recipe_import"),
                {"raw_text": "Existing Recipe\nIngredients\n1 cup flour\nInstructions\nStep 1"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(Recipe.objects.count(), 1)

    def test_get_supported_websites_returns_list(self):
        """get_supported_websites returns a sorted list of domains."""
        sites = get_supported_websites()
        self.assertIsInstance(sites, list)
        self.assertGreater(len(sites), 0)
        self.assertEqual(sites, sorted(sites))

    def test_get_supported_websites_cached(self):
        """get_supported_websites caches and returns the same list."""
        sites1 = get_supported_websites()
        sites2 = get_supported_websites()
        self.assertIs(sites1, sites2)

    def test_parse_recipe_text_empty_string(self):
        """Empty text parsing should return defaults."""
        result = parse_recipe_text("")
        self.assertEqual(result["title"], "Imported Recipe")
        self.assertEqual(result["servings"], 4)
        self.assertEqual(result["ingredients"], [])
        self.assertEqual(result["steps"], [])

    def test_import_view_no_ingredients_rejected(self):
        """Import with no ingredients shows error message."""
        mock_data = {
            "title": "Empty Recipe",
            "servings": 4,
            "steps": [{"text": "Do something", "duration_minutes": None}],
            "ingredients": [],
            "tags_list": [],
            "image_path": "",
        }
        with patch("recipes.views_recipes.parse_recipe_text", return_value=mock_data):
            response = self.client.post(
                reverse("recipe_import"),
                {"raw_text": "Empty Recipe\nIngredients\nInstructions\nDo something"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No ingredients could be extracted")

    def test_import_view_no_steps_rejected(self):
        """Import with no steps shows error message."""
        mock_data = {
            "title": "No Steps Recipe",
            "servings": 4,
            "steps": [],
            "ingredients": [{"name": "flour", "quantity": "1.00", "unit": "item", "note": "", "category": ""}],
            "tags_list": [],
            "image_path": "",
        }
        with patch("recipes.views_recipes.parse_recipe_text", return_value=mock_data):
            response = self.client.post(
                reverse("recipe_import"),
                {"raw_text": "No Steps Recipe\nIngredients\nflour\nInstructions"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No steps could be extracted")

    def test_fallback_parse_ingredients_from_wprm(self):
        """_fallback_parse_ingredients extracts ingredients from WPRM-style HTML."""
        from bs4 import BeautifulSoup
        from recipes.parser import _fallback_parse_ingredients, _load_ingredient_cache
        from recipes.services import load_normalization_cache

        html = '''
        <div class="wprm-recipe-ingredients-container">
          <ul class="wprm-recipe-ingredients">
            <li class="wprm-recipe-ingredient">
              <span class="wprm-recipe-ingredient-amount">2</span>
              <span class="wprm-recipe-ingredient-unit">cups</span>
              <span class="wprm-recipe-ingredient-name">flour</span>
            </li>
            <li class="wprm-recipe-ingredient">
              <span class="wprm-recipe-ingredient-amount">1</span>
              <span class="wprm-recipe-ingredient-unit">tbsp</span>
              <span class="wprm-recipe-ingredient-name">sugar</span>
            </li>
          </ul>
        </div>
        '''
        soup = BeautifulSoup(html, "html.parser")
        ingredient_cache = _load_ingredient_cache()
        normalization_cache = load_normalization_cache()
        result = _fallback_parse_ingredients(soup, ingredient_cache, normalization_cache)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "flour")
        self.assertEqual(result[1]["name"], "sugar")

    def test_fallback_parse_steps_from_wprm(self):
        """_fallback_parse_steps extracts steps from WPRM-style HTML."""
        from bs4 import BeautifulSoup
        from recipes.parser import _fallback_parse_steps

        html = '''
        <div class="wprm-recipe-instructions-container">
          <ol class="wprm-recipe-instructions">
            <li class="wprm-recipe-instruction">
              <span>Mix flour and sugar together.</span>
            </li>
            <li class="wprm-recipe-instruction">
              <span>Bake for 30 minutes.</span>
            </li>
          </ol>
        </div>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _fallback_parse_steps(soup)
        self.assertEqual(len(result), 2)

    def test_fallback_parse_ingredients_from_jsonld(self):
        """_fallback_parse_ingredients extracts from JSON-LD when WPRM absent."""
        from bs4 import BeautifulSoup
        from recipes.parser import _fallback_parse_ingredients, _load_ingredient_cache
        from recipes.services import load_normalization_cache

        html = '''
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Recipe",
          "recipeIngredient": ["2 cups flour", "1 tbsp sugar"]
        }
        </script>
        '''
        soup = BeautifulSoup(html, "html.parser")
        ingredient_cache = _load_ingredient_cache()
        normalization_cache = load_normalization_cache()
        result = _fallback_parse_ingredients(soup, ingredient_cache, normalization_cache)
        self.assertGreaterEqual(len(result), 1)


class SmartQuantityDisplayTests(TestCase):
    """Tests for smart_quantity_display and shopping_item_display filters."""

    def _item(self, quantity, unit):
        return SimpleNamespace(quantity=quantity, unit=unit)

    # g to kg conversions

    def test_1000g_converts_to_1_kg(self):
        item = self._item(1000, "g")
        self.assertEqual(smart_quantity_display(item), "1 kg")

    def test_1500g_converts_to_1_5_kg(self):
        item = self._item(1500, "g")
        self.assertEqual(smart_quantity_display(item), "1.5 kg")

    def test_500g_stays_as_500_g(self):
        item = self._item(500, "g")
        self.assertEqual(smart_quantity_display(item), "500 g")

    def test_2000g_converts_to_2_kg(self):
        item = self._item(2000, "g")
        self.assertEqual(smart_quantity_display(item), "2 kg")

    # ml to L conversions

    def test_1000ml_converts_to_1_L(self):
        item = self._item(1000, "ml")
        self.assertEqual(smart_quantity_display(item), "1 L")

    def test_1500ml_converts_to_1_5_L(self):
        item = self._item(1500, "ml")
        self.assertEqual(smart_quantity_display(item), "1.5 L")

    def test_500ml_stays_as_500_ml(self):
        item = self._item(500, "ml")
        self.assertEqual(smart_quantity_display(item), "500 ml")

    def test_250ml_stays_as_250_ml(self):
        item = self._item(250, "ml")
        self.assertEqual(smart_quantity_display(item), "250 ml")

    # item unit hides label

    def test_item_unit_hides_label(self):
        item = self._item(3, "item")
        self.assertEqual(smart_quantity_display(item), "3")

    def test_item_unit_decimal_hides_label(self):
        item = self._item(Decimal("1.5"), "item")
        self.assertEqual(smart_quantity_display(item), "1.5")

    # other units display as-is

    def test_tbsp_unit(self):
        item = self._item(2, "tbsp")
        self.assertEqual(smart_quantity_display(item), "2 tbsp")

    def test_cup_unit(self):
        item = self._item(1, "cup")
        self.assertEqual(smart_quantity_display(item), "1 cup")

    def test_kg_unit(self):
        item = self._item(Decimal("0.5"), "kg")
        self.assertEqual(smart_quantity_display(item), "0.5 kg")

    def test_L_unit(self):
        item = self._item(Decimal("1.5"), "L")
        self.assertEqual(smart_quantity_display(item), "1.5 L")

    # decimal edge cases

    def test_1250g_converts_to_1_25_kg(self):
        item = self._item(1250, "g")
        self.assertEqual(smart_quantity_display(item), "1.25 kg")

    def test_250g_stays_as_250_g_decimal(self):
        item = self._item(250, "g")
        self.assertEqual(smart_quantity_display(item), "250 g")

    def test_decimal_1000g_converts_to_1_kg(self):
        item = self._item(Decimal("1000"), "g")
        self.assertEqual(smart_quantity_display(item), "1 kg")

    # shopping_item_display alias

    def test_shopping_item_display_alias_g_to_kg(self):
        item = self._item(1500, "g")
        self.assertEqual(shopping_item_display(item), "1.5 kg")

    def test_shopping_item_display_alias_ml_to_L(self):
        item = self._item(2000, "ml")
        self.assertEqual(shopping_item_display(item), "2 L")

    def test_shopping_item_display_alias_other_unit(self):
        item = self._item(3, "tsp")
        self.assertEqual(shopping_item_display(item), "3 tsp")

    def test_shopping_item_display_alias_item_unit(self):
        item = self._item(5, "item")
        self.assertEqual(shopping_item_display(item), "5")

import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    AppSetting,
    Ingredient,
    MealPlanEntry,
    Recipe,
    RecipeIngredient,
    ShoppingListItem,
    Supermarket,
    SupermarketSection,
    Unit,
)
from .services import build_shopping_list
from .views import start_of_week


MEDIA_ROOT = tempfile.mkdtemp()


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
                "steps": "Toast bread.\nAdd beans.",
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
                "steps": "Toast bread.\nAdd beans.",
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
                "steps": "Toast bread.\nAdd beans.",
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
                "steps": "Toast bread.\nAdd beans.",
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
                "steps": "Toast bread.\nAdd beans.",
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
                "steps": "Toast bread.\nAdd beans.",
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

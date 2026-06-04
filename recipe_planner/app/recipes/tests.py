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
    ShoppingList,
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

    def test_parse_ingredient_line(self):
        from .parser import parse_ingredient_line
        
        # Test fractions
        res = parse_ingredient_line("1/2 cup flour, sifted")
        self.assertEqual(res["name"], "flour")
        self.assertEqual(res["quantity"], "0.50")
        self.assertEqual(res["unit"], Unit.ITEM)
        self.assertEqual(res["note"], "cup, sifted")
        
        # Test unicode fractions
        res2 = parse_ingredient_line("1½ tsp salt")
        self.assertEqual(res2["name"], "salt")
        self.assertEqual(res2["quantity"], "1.50")
        self.assertEqual(res2["unit"], Unit.TEASPOON)
        
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
        from unittest.mock import patch
        
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

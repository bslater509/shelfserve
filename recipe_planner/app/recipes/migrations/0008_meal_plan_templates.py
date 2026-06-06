# Generated manually for ShelfServe planner templates.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0007_feature_refinements"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealPlanTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="MealPlanTemplateEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day_offset", models.PositiveSmallIntegerField()),
                (
                    "meal_slot",
                    models.CharField(
                        choices=[("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner")],
                        max_length=20,
                    ),
                ),
                (
                    "servings",
                    models.PositiveIntegerField(
                        default=4,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=160)),
                (
                    "recipe",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="recipes.recipe"),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="recipes.mealplantemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["day_offset", "meal_slot"],
                "unique_together": {("template", "day_offset", "meal_slot")},
            },
        ),
    ]

# Generated manually for ShelfServe feature refinements.

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0006_mealplanentry_pantry_consumed_at_pantryitem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mealplanentry",
            name="note",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="pantryitem",
            name="low_stock_threshold",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="recipe",
            name="cook_minutes",
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AddField(
            model_name="recipe",
            name="favorite",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recipe",
            name="last_cooked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recipe",
            name="prep_minutes",
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AddField(
            model_name="recipe",
            name="source_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="shoppinglistitem",
            name="pantry_used_quantity",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=10),
        ),
        migrations.AddField(
            model_name="shoppinglistitem",
            name="pantry_used_unit",
            field=models.CharField(
                blank=True,
                choices=[
                    ("g", "g"),
                    ("kg", "kg"),
                    ("ml", "ml"),
                    ("l", "l"),
                    ("tsp", "tsp"),
                    ("tbsp", "tbsp"),
                    ("item", "item"),
                    ("pack", "pack"),
                ],
                max_length=8,
            ),
        ),
    ]

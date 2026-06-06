from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Unit(models.TextChoices):
    GRAM = "g", "g"
    KILOGRAM = "kg", "kg"
    MILLILITRE = "ml", "ml"
    LITRE = "l", "l"
    TEASPOON = "tsp", "tsp"
    TABLESPOON = "tbsp", "tbsp"
    ITEM = "item", "item"
    PACK = "pack", "pack"


UNIT_GROUPS = {
    Unit.GRAM: ("mass", Decimal("1"), Unit.GRAM),
    Unit.KILOGRAM: ("mass", Decimal("1000"), Unit.GRAM),
    Unit.MILLILITRE: ("volume", Decimal("1"), Unit.MILLILITRE),
    Unit.LITRE: ("volume", Decimal("1000"), Unit.MILLILITRE),
    Unit.TEASPOON: ("volume", Decimal("5"), Unit.MILLILITRE),
    Unit.TABLESPOON: ("volume", Decimal("15"), Unit.MILLILITRE),
    Unit.ITEM: ("item", Decimal("1"), Unit.ITEM),
    Unit.PACK: ("pack", Decimal("1"), Unit.PACK),
}


MEAL_SLOTS = (
    ("breakfast", "Breakfast"),
    ("lunch", "Lunch"),
    ("dinner", "Dinner"),
)


class AppSetting(models.Model):
    WEEK_START_CHOICES = (
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    )

    week_start = models.PositiveSmallIntegerField(choices=WEEK_START_CHOICES, default=0)

    @classmethod
    def current(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    def __str__(self):
        return "ShelfServe settings"


class Tag(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(
        max_length=120,
        blank=True,
        help_text="Supermarket section, such as Fruit & veg or Bakery.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    title = models.CharField(max_length=160)
    image = models.ImageField(upload_to="recipes/", blank=True)
    servings = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1)])
    prep_minutes = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    cook_minutes = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    source_url = models.URLField(blank=True)
    favorite = models.BooleanField(default=False)
    last_cooked_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("recipe_detail", args=[self.pk])


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, related_name="ingredients", on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    unit = models.CharField(max_length=8, choices=Unit.choices)
    note = models.CharField(max_length=160, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "ingredient__name"]

    def __str__(self):
        return f"{self.quantity:g} {self.unit} {self.ingredient.name}"


class RecipeStep(models.Model):
    recipe = models.ForeignKey(Recipe, related_name="steps", on_delete=models.CASCADE)
    text = models.TextField()
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Step {self.order + 1} for {self.recipe.title}"



class Supermarket(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupermarketSection(models.Model):
    supermarket = models.ForeignKey(Supermarket, related_name="sections", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        unique_together = ("supermarket", "name")

    def __str__(self):
        return f"{self.supermarket}: {self.name}"


class MealPlanEntry(models.Model):
    date = models.DateField()
    meal_slot = models.CharField(max_length=20, choices=MEAL_SLOTS)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE)
    servings = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1)])
    note = models.CharField(max_length=160, blank=True)
    pantry_consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date", "meal_slot"]
        unique_together = ("date", "meal_slot")

    def __str__(self):
        return f"{self.date} {self.meal_slot}: {self.recipe}"


class PantryItem(models.Model):
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    unit = models.CharField(max_length=8, choices=Unit.choices)
    low_stock_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    note = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ingredient__name", "unit"]
        unique_together = ("ingredient", "unit")

    def __str__(self):
        return f"{self.quantity:g} {self.unit} {self.ingredient.name}"


class PantryAdjustment(models.Model):
    meal_plan_entry = models.ForeignKey(MealPlanEntry, related_name="pantry_adjustments", on_delete=models.CASCADE)
    pantry_item = models.ForeignKey(PantryItem, null=True, blank=True, on_delete=models.SET_NULL)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    unit = models.CharField(max_length=8, choices=Unit.choices)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["ingredient__name", "unit", "created_at"]

    def __str__(self):
        return f"{self.quantity:g} {self.unit} {self.ingredient.name}"


class ShoppingList(models.Model):
    supermarket = models.ForeignKey(Supermarket, on_delete=models.PROTECT)
    week_start = models.DateField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.supermarket} list for {self.week_start}"


class ShoppingListItem(models.Model):
    shopping_list = models.ForeignKey(ShoppingList, related_name="items", on_delete=models.CASCADE)
    section_name = models.CharField(max_length=120)
    section_order = models.PositiveIntegerField(default=9999)
    ingredient_name = models.CharField(max_length=120)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=8, choices=Unit.choices)
    pantry_used_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    pantry_used_unit = models.CharField(max_length=8, choices=Unit.choices, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    checked = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)

    class Meta:
        ordering = ["section_order", "section_name", "ingredient_name", "unit"]

    def __str__(self):
        return f"{self.quantity:g} {self.unit} {self.ingredient_name}"

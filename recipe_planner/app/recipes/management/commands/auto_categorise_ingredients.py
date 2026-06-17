"""
Management command to auto-categorise ingredients by matching their names
against keyword patterns from ``recipes.ingredient_keywords.CATEGORY_KEYWORDS``.

Usage::

    python manage.py auto_categorise_ingredients [--dry-run] [--limit N] [--force]

How it works
------------

1. Load ``CATEGORY_KEYWORDS`` (category name -> ordered keyword list).
2. Map near-duplicate categories to their canonical names.
3. For each (uncategorised, or all if ``--force``) ingredient, lower-case
   its normalised name and scan against every keyword in priority order.
4. First match wins: if the name starts with the keyword (followed by a
   space, comma, or end-of-string) or the keyword appears as a whole word
   inside the name (``\\b`` regex), assign that category.
5. If no keyword matches, the ingredient is assigned to "Other".
6. ``IngredientCategory`` rows are created via ``get_or_create`` when a
   category name is not already in the database.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict

from django.core.management.base import BaseCommand
from django.db import transaction

from recipes.ingredient_keywords import CATEGORY_KEYWORDS
from recipes.models import Ingredient, IngredientCategory
from recipes.services import normalise_name

# ---------------------------------------------------------------------------
# Near-duplicate category routing
# ---------------------------------------------------------------------------

NEAR_DUPLICATE_MAP = {
    "Condiments": "Sauces & Condiments",
    "Oils": "Oils & Vinegars",
    "Pasta": "Pasta & Rice",
    "Tins": "Pantry",
    "Vegetables": "Fruit & Vegetables",
}


def canonical_category(name: str) -> str:
    """Return the canonical category name, routing near-duplicates."""
    return NEAR_DUPLICATE_MAP.get(name, name)


def match_ingredient_to_category(
    name_lower: str,
    keywords_dict: Dict[str, list],
) -> str:
    """Match a lowercased ingredient name against keyword->category mapping.

    Returns the canonical category name, or ``"Other"`` if no keyword
    matches.  Keywords are ordered by priority; first match wins.
    """
    for category_name, keywords in keywords_dict.items():
        if category_name == "Other":
            continue
        canonical = canonical_category(category_name)
        for kw in keywords:
            # Match if name starts with the keyword (followed by space,
            # comma, or end-of-string) ...
            if (
                name_lower == kw
                or name_lower.startswith(kw + " ")
                or name_lower.startswith(kw + ",")
            ):
                return canonical
            # ... or the keyword appears as a whole word inside the name.
            if re.search(r"\b" + re.escape(kw) + r"\b", name_lower):
                return canonical
    return "Other"


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Auto-categorise ingredients by matching names against keyword "
        "patterns from recipes.ingredient_keywords.CATEGORY_KEYWORDS."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving to database.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            help="Maximum number of ingredients to process.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-categorise ingredients that already have a category.",
        )

    def handle(self, **options):
        dry_run: bool = options.get("dry_run", False)
        limit: int | None = options.get("limit")
        force: bool = options.get("force", False)
        verbosity: int = options.get("verbosity", 1)

        # ---- 1. Build category-name -> IngredientCategory map ---------
        category_map: Dict[str, IngredientCategory] = {}
        created_categories: list[str] = []

        for cat_name in CATEGORY_KEYWORDS:
            canonical = canonical_category(cat_name)
            obj, created = IngredientCategory.objects.get_or_create(
                name=canonical
            )
            category_map[cat_name] = obj
            if created:
                created_categories.append(canonical)

        if created_categories:
            self.stdout.write("Created categories:")
            for c in created_categories:
                self.stdout.write(f"  + {c}")
            self.stdout.write("")

        # ---- 2. Fetch ingredients to process --------------------------
        qs = Ingredient.objects.select_related("category").order_by("name")
        if not force:
            qs = qs.filter(category__isnull=True)

        already_categorised = Ingredient.objects.filter(
            category__isnull=False
        ).count()

        if limit:
            qs = qs[:limit]

        ingredients = list(qs)

        if not ingredients:
            self.stdout.write("No ingredients to process.")
            return

        if force:
            self.stdout.write(
                f"Processing {len(ingredients)} ingredient(s) "
                f"(force mode — re-categorising all).\n"
            )
        else:
            self.stdout.write(
                f"Processing {len(ingredients)} uncategorised "
                f"ingredient(s) (of {already_categorised} already "
                f"categorised).\n"
            )

        # ---- 3. Match & assign ----------------------------------------
        categorised_count = 0
        per_category: Counter = Counter()

        with transaction.atomic():
            for ing in ingredients:
                name_lower = normalise_name(ing.name).lower()
                matched = match_ingredient_to_category(
                    name_lower, CATEGORY_KEYWORDS
                )
                # matched is always a canonical category name (or "Other")
                cat_obj = category_map.get(matched)
                if cat_obj is None:
                    # create "Other" on the fly if not in keyword dict
                    cat_obj, _ = IngredientCategory.objects.get_or_create(
                        name="Other"
                    )
                    category_map["Other"] = cat_obj

                if not dry_run:
                    ing.category = cat_obj
                    ing.save(update_fields=["category"])

                categorised_count += 1
                per_category[matched] += 1
                if verbosity >= 2:
                    self.stdout.write(
                        f'  "{ing.name}" -> {matched}'
                    )

            if dry_run:
                transaction.set_rollback(True)

        # ---- 4. Print summary -----------------------------------------
        still_uncategorised = Ingredient.objects.filter(
            category__isnull=True
        ).count()

        self.stdout.write("")
        self.stdout.write("=" * 60)
        if dry_run:
            self.stdout.write("DRY RUN — no changes saved.")
        self.stdout.write(f"Done. Categorised: {categorised_count}, "
                          f"Already categorised: {already_categorised}, "
                          f"Still uncategorised: {still_uncategorised}")
        self.stdout.write("")
        self.stdout.write("Category distribution:")
        for cat_name, count in per_category.most_common():
            self.stdout.write(f"  {cat_name}: {count}")
        self.stdout.write("=" * 60)

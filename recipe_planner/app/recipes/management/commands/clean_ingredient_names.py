"""
Management command to clean polluted ingredient names.

Strips leading quantities, units, container patterns and trailing
unmatched parenthetical marks from ingredient names, normalises
whitespace, and deduplicates after cleaning.

Usage::

    python manage.py clean_ingredient_names [--dry-run] [--limit N]

Examples of pollution cleaned
-----------------------------
- ``2 clove sun-dried tomatoes``  →  ``sun-dried tomatoes``
- ``/ 1 lb chicken breast``       →  ``chicken breast``
- ``/ 1 lb chicken breast )``     →  ``chicken breast``
- ``14-ounce can crushed tomatoes`` → ``crushed tomatoes``
- ``16 oz. bag coleslaw mix``     →  ``coleslaw mix``
- ``2 broccoli``                  →  ``broccoli``
- ``195g cans tuna drained``      →  ``tuna drained``
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction

from recipes.models import Ingredient, PantryAdjustment, PantryItem, RecipeIngredient
from recipes.services import normalise_name

# ---------------------------------------------------------------------------
# Unit & container word lists (drawn from parser.UNIT_MAPPING & models.Unit)
# ---------------------------------------------------------------------------

# Units that can attach directly to a number ("195g", "500ml", "16oz")
_ATTACHED_UNITS = r"g|kg|ml|l|oz|lb"

# All unit words (space-separated after the number)
_UNIT_WORDS = [
    "g", "gram", "grams",
    "kg", "kilogram", "kilograms",
    "ml", "milliliter", "milliliters", "millilitre", "millilitres",
    "l", "liter", "liters", "litre", "litres",
    "tsp", "tsp.", "teaspoon", "teaspoons",
    "tbsp", "tbsp.", "tablespoon", "tablespoons",
    "cup", "cups",
    "clove", "cloves",
    "pinch", "pinches",
    "slice", "slices",
    "piece", "pieces",
    "head", "heads",
    "bunch", "bunches",
    "stalk", "stalks",
    "pack", "packs", "package", "packages",
    "box", "boxes",
    "can", "cans", "tin", "tins",
    "bag", "bags",
    "carton", "cartons",
    "bottle", "bottles",
    "jar", "jars",
    "rasher", "rashers",
    "lb", "lbs", "pound", "pounds",
    "oz", "ounce", "ounces",
]
_UNIT_ALT = "|".join(re.escape(w) for w in sorted(_UNIT_WORDS, key=len, reverse=True))

# Unit adjectives (from parser.UNIT_ADJECTIVES)
# e.g. "4 heaped piece …", "1 level cup …"
_UNIT_ADJECTIVES_WORDS = ["heaped", "heaping", "level", "rounded", "scant", "generous"]
_UNIT_ADJ_ALT = "|".join(_UNIT_ADJECTIVES_WORDS)

# Container words (e.g., "14-ounce **can**", "195g **cans**", "1 lb **bag**", "16-ounce **loaf**")
_CONTAINER_WORDS = [
    "can", "cans", "tin", "tins",
    "bag", "bags",
    "jar", "jars",
    "bottle", "bottles",
    "box", "boxes",
    "carton", "cartons",
    "pack", "packs",
    "loaf", "loaves",
]
_CONTAINER_ALT = "|".join(re.escape(w) for w in sorted(_CONTAINER_WORDS, key=len, reverse=True))

# ---------------------------------------------------------------------------
# Compiled regex patterns (applied in order, each strips ONE leading match)
# ---------------------------------------------------------------------------

# 1  "14-ounce can …", "15.5-oz. can …", "16-oz bag …"
_RE_DASH_OUNCE = re.compile(
    r"^\d+(?:\.\d+)?\s*-\s*(?:ounce|oz)\.?\s+"
    r"(?:(?:" + _CONTAINER_ALT + r")\.?\s+)?"
    r"(?:of\s+)?",
    re.IGNORECASE,
)

# 2  "195g cans …", "500ml bottle …", "16 oz. bag …" (attached or spaced abbrev)
_RE_ATTACHED_UNIT = re.compile(
    r"^\d+(?:\.\d+)?\s*"               # number
    r"(?:" + _ATTACHED_UNITS + r")"     # unit abbreviation (g, kg, ml, l, oz, lb)
    r"\.?\s+"                            # optional dot + whitespace
    r"(?:(?:" + _CONTAINER_ALT + r")\.?\s+)?"
    r"(?:of\s+)?",
    re.IGNORECASE,
)

# 3  "2 clove sun-dried …", "1 lb chicken …", "4 heaped piece …", "3 cups flour …"
_RE_NUMBER_UNIT = re.compile(
    r"^\d+(?:\.\d+)?\s+"                # number + space
    r"(?:(?:" + _UNIT_ADJ_ALT + r")\s+)?"  # optional adjective (heaped, level, etc.)
    r"(?:" + _UNIT_ALT + r")"           # unit word
    r"\.?\s+"                            # optional dot + whitespace
    r"(?:(?:" + _CONTAINER_ALT + r")\.?\s+)?"
    r"(?:of\s+)?",
    re.IGNORECASE,
)

# 4  Bare leading number: "2 broccoli", "3 eggs"
_RE_BARE_NUMBER = re.compile(r"^\d+(?:\.\d+)?\s+")

# 5  Leading noise: "/ 1 lb …", "/ flour …"
_RE_LEADING_NOISE = re.compile(r"^[\/]\s+")

# 6  Trailing matched parenthetical "(…)" — useful recipe notes to strip
_RE_TRAILING_MATCHED_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


# ---------------------------------------------------------------------------
# cleaning helpers
# ---------------------------------------------------------------------------


def _unmatched_rstrip(text: str, close_char: str, open_char: str) -> str:
    """Strip trailing *close_char* only when *open_char* is absent."""
    if text.endswith(close_char) and open_char not in text:
        return text.rstrip(close_char).strip()
    return text


def clean_name(name: str) -> Tuple[str, bool]:
    """Return ``(cleaned_name, was_modified)`` for a single ingredient name.

    Returns the original *name* unchanged (and ``was_modified=False``)
    when the cleaned result is empty or whitespace-only.
    """
    original = name
    cleaned = name.strip()

    # Pass 1: strip leading "/ "
    cleaned, _modified = re.subn(_RE_LEADING_NOISE, "", cleaned, count=1)

    # Pass 2: strip "14-ounce can …", "16-oz bag …"
    cleaned, _m = re.subn(_RE_DASH_OUNCE, "", cleaned, count=1)

    # Pass 3: strip "195g cans …", "16 oz. bag …" (abbreviated unit)
    cleaned, _m = re.subn(_RE_ATTACHED_UNIT, "", cleaned, count=1)

    # Pass 4: strip "2 clove …", "1 lb …", "3 cups …" (number + unit word)
    cleaned, _m = re.subn(_RE_NUMBER_UNIT, "", cleaned, count=1)

    # Pass 5: strip bare leading number "2 broccoli"
    cleaned, _m = re.subn(_RE_BARE_NUMBER, "", cleaned, count=1)

    # Pass 5b: strip leading "of " left over from "2 cups of flour"
    cleaned = re.sub(r"^of\s+", "", cleaned, count=1, flags=re.IGNORECASE)

    # Pass 5c: strip leading container word + "of"
    # e.g. "loaf of Italian bread" -> "Italian bread"
    cleaned = re.sub(
        r"^(?:" + _CONTAINER_ALT + r")\s+of\s+",
        "",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    )

    # Pass 6: strip trailing matched parenthetical "(…)"
    cleaned = _RE_TRAILING_MATCHED_PAREN.sub("", cleaned)

    # Pass 7: strip trailing unmatched ")" / "]" / "(" / "["
    # Only strip if the matching opener is not present in the string.
    cleaned = _unmatched_rstrip(cleaned, ")", "(")
    cleaned = _unmatched_rstrip(cleaned, "]", "[")
    cleaned = _unmatched_rstrip(cleaned, "(", ")")
    cleaned = _unmatched_rstrip(cleaned, "[", "]")

    # Normalise whitespace
    cleaned = normalise_name(cleaned)

    if not cleaned:
        return (original, False)

    return (cleaned, cleaned != original)


# ---------------------------------------------------------------------------
# merge helper
# ---------------------------------------------------------------------------


def merge_ingredient(
    source: Ingredient,
    target: Ingredient,
) -> int:
    """Re-point all FK references from *source* to *target*, then delete *source*.

    Updates ``RecipeIngredient``, ``PantryItem``, ``PantryAdjustment``
    rows and any ingredient whose ``canonical`` FK points to *source*.

    Returns the number of records updated.
    """
    updated = 0

    updated += RecipeIngredient.objects.filter(ingredient=source).update(ingredient=target)
    updated += PantryItem.objects.filter(ingredient=source).update(ingredient=target)
    updated += PantryAdjustment.objects.filter(ingredient=source).update(ingredient=target)
    updated += Ingredient.objects.filter(canonical=source).update(canonical=target)

    source.delete()
    return updated


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Strip leading quantities/units/containers and trailing "
        "parenthetical noise from ingredient names, then deduplicate."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without modifying the database.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of ingredients to process (default: all).",
        )

    def handle(self, **options):
        dry_run: bool = options.get("dry_run", False)
        limit: Optional[int] = options.get("limit")

        if dry_run:
            self.stdout.write("=== Ingredient Name Cleanup (DRY RUN) ===\n")
        else:
            self.stdout.write("=== Ingredient Name Cleanup ===\n")

        # ---- fetch ingredients ------------------------------------------
        total = Ingredient.objects.count()
        qs = Ingredient.objects.order_by("pk")
        if limit is not None:
            qs = qs[:limit]

        ingredients: List[Ingredient] = list(qs)
        self.stdout.write(f"Total ingredients in DB : {total}")
        self.stdout.write(f"Processing              : {len(ingredients)}")
        if limit is not None:
            self.stdout.write(f"Limit                   : {limit}")
        self.stdout.write("")

        # ---- process ---------------------------------------------------
        cleaned_count = 0
        merged_count = 0
        skipped_count = 0
        empty_count = 0
        total_refs_updated = 0
        unchanged_count = 0

        with transaction.atomic():
            for ingredient in ingredients:
                new_name, changed = clean_name(ingredient.name)

                if not changed:
                    unchanged_count += 1
                    continue

                if not new_name:
                    # cleaned to empty — flag for review
                    empty_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'  EMPTY: "{ingredient.name}" cleaned to empty — skipped'
                        )
                    )
                    continue

                if dry_run:
                    # Check if this cleaned name would collide
                    collision = (
                        Ingredient.objects
                        .filter(name__iexact=new_name)
                        .exclude(pk=ingredient.pk)
                        .first()
                    )
                    if collision:
                        self.stdout.write(
                            f'  WOULD MERGE: "{ingredient.name}" '
                            f'-> "{collision.name}" (pk={collision.pk})'
                        )
                        merged_count += 1
                    else:
                        self.stdout.write(
                            f'  WOULD CLEAN: "{ingredient.name}" '
                            f'-> "{new_name}"'
                        )
                        cleaned_count += 1
                    skipped_count += 1
                    continue

                # ---- apply (non-dry-run) ---------------------------------
                existing = (
                    Ingredient.objects
                    .filter(name__iexact=new_name)
                    .exclude(pk=ingredient.pk)
                    .order_by("pk")
                    .first()
                )

                if existing:
                    # Keep the ingredient with the lower pk.
                    # Delete the duplicate FIRST so the unique constraint
                    # won't fire when we rename the keeper.
                    if ingredient.pk < existing.pk:
                        keeper, dupe = ingredient, existing
                        refs = merge_ingredient(dupe, keeper)
                        if keeper.name != new_name:
                            keeper.name = new_name
                            keeper.save(update_fields=["name"])
                    else:
                        keeper, dupe = existing, ingredient
                        refs = merge_ingredient(dupe, keeper)

                    total_refs_updated += refs
                    merged_count += 1
                    self.stdout.write(
                        f'  MERGED: "{dupe.name}" -> "{keeper.name}" '
                        f"({refs} refs updated, deleted pk={dupe.pk})"
                    )
                else:
                    # Simple rename
                    old_name = ingredient.name
                    ingredient.name = new_name
                    ingredient.save(update_fields=["name"])
                    cleaned_count += 1
                    self.stdout.write(
                        f'  CLEANED: "{old_name}" -> "{new_name}"'
                    )

            if dry_run:
                transaction.set_rollback(True)

        # ---- summary ----------------------------------------------------
        self.stdout.write("")
        self.stdout.write("=" * 64)
        if dry_run:
            self.stdout.write("DRY RUN — no changes saved.")
        self.stdout.write(f"{'Processed':<30} {len(ingredients):>5}")
        self.stdout.write(f"{'Names cleaned':<30} {cleaned_count:>5}")
        self.stdout.write(f"{'Names unchanged':<30} {unchanged_count:>5}")
        self.stdout.write(f"{'Duplicates merged':<30} {merged_count:>5}")
        self.stdout.write(f"{'References updated':<30} {total_refs_updated:>5}")
        if empty_count:
            self.stdout.write(
                self.style.WARNING(
                    f"{'Empty after cleaning':<30} {empty_count:>5}  (flagged for review)"
                )
            )
        self.stdout.write("=" * 64)

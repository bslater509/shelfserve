"""
Management command to detect and merge duplicate/synonymous ingredients
by setting the ``canonical`` ForeignKey on variant ingredients.

Usage::

    python manage.py auto_merge_ingredients [--dry-run]

Detection rules
---------------

1. **Singular/plural** — e.g. "tomato" / "tomatoes" → singular is
   canonical.  Suffix stripping: ``ies``→``y``, ``ves``→``f``,
   ``es``→``""``, ``s``→``""`` (but not ``ss`` or ``us``).

2. **Qualifier stripping** — e.g. "ground coriander" / "coriander" →
   unqualified name is canonical.  Strips leading qualifier words from
   a predefined list.

3. **IngredientNormalization hints** — if a rule maps X→Y and both X
   and Y exist as ingredients, Y becomes canonical for X.

4. **Case-insensitive** — all comparisons use ``.lower()``.

5. **Group merge** — when components overlap (A→B and B→C), all three
   are merged into one group.  Within each group the ingredient with
   the **smallest pk** is chosen as canonical.

No ingredients are deleted — only the ``canonical`` FK is updated.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction

from recipes.models import Ingredient, IngredientNormalization

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

QUALIFIERS: List[str] = [
    "ground",
    "fresh",
    "dried",
    "frozen",
    "organic",
    "whole",
    "crushed",
    "minced",
    "chopped",
    "grated",
    "sliced",
    "diced",
    "shredded",
    "cooked",
    "raw",
    "smoked",
    "roasted",
    "toasted",
    "tinned",
    "canned",
    "jarred",
    "pickled",
    "salted",
    "unsalted",
    "seedless",
    "skinless",
    "boneless",
    "free-range",
    "large",
    "small",
    "medium",
    "ripe",
    "baby",
    "young",
    "aged",
    "mature",
]

# ---------------------------------------------------------------------------
# data helpers
# ---------------------------------------------------------------------------


@dataclass
class MergePair:
    """A detected variant→canonical relationship."""

    variant_name: str
    canonical_name: str
    merge_type: str  # "singular/plural", "qualifier", "normalization"


# ---------------------------------------------------------------------------
# detection helpers
# ---------------------------------------------------------------------------


def _singularize(name: str) -> Optional[str]:
    """Return a candidate singular form of *name*, or ``None``.

    Transforms common English plural suffixes to their singular
    equivalents.  The caller is responsible for checking whether the
    result actually exists as another ingredient.
    """
    lower = name.lower()
    # ies → y  (berries → berry)
    if lower.endswith("ies") and len(lower) > 3:
        return name[:-3] + "y"
    # ves → f  (loaves → loaf)
    if lower.endswith("ves") and len(lower) > 3:
        return name[:-3] + "f"
    # oes → o  (tomatoes → tomato)
    if lower.endswith("oes") and len(lower) > 3:
        return name[:-2]
    # shes/ches/xes/zes/ses → remove es  (dishes→dish, boxes→box)
    if (
        lower.endswith(("shes", "ches", "xes", "zes", "ses"))
        and len(lower) > 4
    ):
        return name[:-2]
    # es → "" (general)
    if lower.endswith("es") and len(lower) > 3:
        return name[:-2]
    # s → "" (onions → onion) — but not ss (pass) or us (asparagus)
    if lower.endswith("s") and not lower.endswith(("ss", "us")) and len(lower) > 2:
        return name[:-1]
    return None


def _strip_leading_qualifier(name: str) -> List[str]:
    """Return candidates produced by stripping one leading qualifier."""
    candidates: List[str] = []
    lower = name.lower()
    for qual in QUALIFIERS:
        prefix = qual + " "
        if lower.startswith(prefix):
            candidates.append(name[len(prefix) :])
    return candidates


# ---------------------------------------------------------------------------
# detection: build merge pairs
# ---------------------------------------------------------------------------


def _detect_singular_plural(
    ingredients: List[Ingredient],
    name_map: Dict[str, Ingredient],
) -> List[MergePair]:
    """Detect singular/plural pairs among *ingredients*."""
    pairs: List[MergePair] = []
    for ing in ingredients:
        singular = _singularize(ing.name)
        if singular is None:
            continue
        singular_lower = singular.lower()
        if singular_lower == ing.name.lower():
            continue  # no-op
        canonical = name_map.get(singular_lower)
        if canonical is not None and canonical.pk != ing.pk:
            pairs.append(
                MergePair(
                    variant_name=ing.name,
                    canonical_name=canonical.name,
                    merge_type="singular/plural",
                )
            )
    return pairs


def _detect_qualifier(
    ingredients: List[Ingredient],
    name_map: Dict[str, Ingredient],
) -> List[MergePair]:
    """Detect qualifier-stripped pairs among *ingredients*."""
    pairs: List[MergePair] = []
    for ing in ingredients:
        for stripped in _strip_leading_qualifier(ing.name):
            stripped_lower = stripped.lower()
            if stripped_lower == ing.name.lower():
                continue
            canonical = name_map.get(stripped_lower)
            if canonical is not None and canonical.pk != ing.pk:
                pairs.append(
                    MergePair(
                        variant_name=ing.name,
                        canonical_name=canonical.name,
                        merge_type="qualifier",
                    )
                )
    return pairs


def _detect_normalization(
    ingredients: List[Ingredient],
    name_map: Dict[str, Ingredient],
) -> List[MergePair]:
    """Detect pairs where both sides of a normalisation rule exist."""
    pairs: List[MergePair] = []
    rules = IngredientNormalization.objects.values_list(
        "match_pattern", "canonical_name"
    )
    for match_pattern, canonical_name in rules:
        variant = name_map.get(match_pattern.lower())
        canonical = name_map.get(canonical_name.lower())
        if variant is not None and canonical is not None and variant.pk != canonical.pk:
            pairs.append(
                MergePair(
                    variant_name=variant.name,
                    canonical_name=canonical.name,
                    merge_type="normalization",
                )
            )
    return pairs


# ---------------------------------------------------------------------------
# group resolution
# ---------------------------------------------------------------------------


def _resolve_groups(
    pairs: List[MergePair],
    name_map: Dict[str, Ingredient],
) -> Dict[str, Ingredient]:
    """Resolve merge pairs into canonical assignments.

    Builds an undirected graph from *pairs*, finds connected components,
    then picks the ingredient with the smallest pk as canonical for the
    entire component.

    Returns a dict mapping ``name.lower()`` → canonical ``Ingredient``
    for every variant that should be updated.
    """
    # ---- build undirected adjacency graph --------------------------------
    adj: Dict[str, Set[str]] = defaultdict(set)
    for pair in pairs:
        v_lower = pair.variant_name.lower()
        c_lower = pair.canonical_name.lower()
        # only add edges when both names exist in the database
        if v_lower in name_map and c_lower in name_map:
            adj[v_lower].add(c_lower)
            adj[c_lower].add(v_lower)

    # ---- find connected components ---------------------------------------
    visited: Set[str] = set()
    components: List[Set[str]] = []
    for node in adj:
        if node in visited:
            continue
        stack = [node]
        component: Set[str] = set()
        while stack:
            n = stack.pop()
            if n not in visited:
                visited.add(n)
                component.add(n)
                stack.extend(adj[n] - visited)
        if len(component) >= 2:
            components.append(component)

    # ---- pick canonical per component ------------------------------------
    assignments: Dict[str, Ingredient] = {}
    for component in components:
        members = [name_map[name] for name in component]
        members.sort(key=lambda ing: ing.pk)
        canonical = members[0]
        for ing in members[1:]:
            # don't reassign if already pointing to the same canonical
            current = ing.canonical
            if current is None or current.pk != canonical.pk:
                assignments[ing.name.lower()] = canonical

    return assignments


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Detect and merge duplicate/synonymous ingredients by setting "
        "the canonical FK on variant ingredients."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving to database.",
        )

    def handle(self, **options):
        dry_run: bool = options.get("dry_run", False)

        # ---- 1. Load all ingredients -------------------------------------
        ingredients: List[Ingredient] = list(
            Ingredient.objects.all().order_by("pk")
        )
        name_map: Dict[str, Ingredient] = {
            ing.name.lower(): ing for ing in ingredients
        }

        self.stdout.write(
            f"Loaded {len(ingredients)} ingredient(s).\n"
        )

        # ---- 2. Detect merge pairs ---------------------------------------
        sp_pairs = _detect_singular_plural(ingredients, name_map)
        qf_pairs = _detect_qualifier(ingredients, name_map)
        nm_pairs = _detect_normalization(ingredients, name_map)

        all_pairs = sp_pairs + qf_pairs + nm_pairs

        if not all_pairs:
            self.stdout.write("No duplicate/synonymous ingredients detected.")
            return

        self.stdout.write(
            f"Detected {len(all_pairs)} merge candidate(s):\n"
            f"  singular/plural  : {len(sp_pairs)}\n"
            f"  qualifier        : {len(qf_pairs)}\n"
            f"  normalization    : {len(nm_pairs)}\n"
        )

        # ---- 3. Resolve groups -------------------------------------------
        assignments = _resolve_groups(all_pairs, name_map)

        if not assignments:
            self.stdout.write("No merges to apply after group resolution.")
            return

        self.stdout.write(
            f"After group resolution: {len(assignments)} ingredient(s) "
            f"to update.\n"
        )

        # ---- 4. Apply merges ---------------------------------------------
        with transaction.atomic():
            updated = 0
            for name_lower, canonical in assignments.items():
                ing = name_map[name_lower]
                if dry_run:
                    self.stdout.write(
                        f"  {ing.name!r}  →  {canonical.name!r}"
                    )
                else:
                    ing.canonical = canonical
                    ing.save(update_fields=["canonical"])
                updated += 1

            if not dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f"Updated {updated} ingredient(s).")
                )

            if dry_run:
                transaction.set_rollback(True)

        # ---- 5. Print summary by type ------------------------------------
        self.stdout.write("")
        self.stdout.write("=" * 64)
        if dry_run:
            self.stdout.write("DRY RUN — no changes saved.")
        self.stdout.write(f"Total merge candidates detected : {len(all_pairs):>5}")
        self.stdout.write(f"Ingredients to update (after    : {len(assignments):>5}")
        self.stdout.write(f"  group resolution)")

        self._print_typed_summary(sp_pairs, assignments, name_map,
                                  "Singular / plural")
        self._print_typed_summary(qf_pairs, assignments, name_map,
                                  "Qualifier stripping")
        self._print_typed_summary(nm_pairs, assignments, name_map,
                                  "Normalization hints")
        self.stdout.write("=" * 64)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _print_typed_summary(
        self,
        pairs: List[MergePair],
        assignments: Dict[str, Ingredient],
        name_map: Dict[str, Ingredient],
        heading: str,
    ) -> None:
        """Print per-type summary of merges that will be applied."""
        # Find pairs of this type whose variant is actually in assignments
        relevant: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        for pair in pairs:
            v_lower = pair.variant_name.lower()
            if v_lower in assignments:
                canonical_name = assignments[v_lower].name
                entry_key = (pair.variant_name, canonical_name)
                if entry_key not in seen:
                    seen.add(entry_key)
                    relevant.append(entry_key)

        if relevant:
            self.stdout.write("")
            self.stdout.write(f"── {heading} ──")
            for variant_name, canonical_name in sorted(relevant):
                self.stdout.write(f"  {variant_name!r}  →  {canonical_name!r}")

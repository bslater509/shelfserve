# Sync Issues (Unresolved Only)

## SYNC-1: S4.1.1 prefetch_related('steps') NOT applied to recipe_detail
- Severity: LOW
- Files: recipe_planner/app/recipes/views_recipes.py (line 80)
- Problem: Task S4.1.1 "Add prefetch_related('steps') to recipe_detail query" was marked [x] but the code still has only `prefetch_related("tags", "ingredients__ingredient")` without `"steps"`. The query count test (S4.1.2) passes with 4 queries (accepts the non-prefetched steps as an extra query).
- Fix: Add `"steps"` to the `prefetch_related` call in `recipe_detail()`:
  ```python
  Recipe.objects.prefetch_related("tags", "ingredients__ingredient", "steps")
  ```
- Status: pending

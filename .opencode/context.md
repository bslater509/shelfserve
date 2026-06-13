# Project Context - Meal Slot Toggle Feature

## Summary
Added per-slot meal type toggle in Settings to enable/disable breakfast, lunch, or dinner slots. Disabled slots are hidden from planner and dashboard.

## Changes Made

### Model (`recipes/models.py`)
- Added `enabled_slots = models.JSONField(default=list)` to `AppSetting`
- Added `MEAL_SLOT_KEYS = [k for k, _v in MEAL_SLOTS]` at module level
- Added `active_meal_slots` property → returns filtered `MEAL_SLOTS` (empty list = all enabled for backward compat)

### Form (`recipes/forms.py`)
- Added `enabled_slots` as `MultipleChoiceField` with `CheckboxSelectMultiple` widget
- Override `__init__` to set initial from instance
- Override `save()` to write list to `instance.enabled_slots`

### Planner View (`views_planner.py`)
- Removed `MEAL_SLOTS` import
- Changed `"meal_slots"` context to `settings.active_meal_slots`
- Pass `enabled_slots=settings.active_meal_slots` to `save_planner_entries()`

### View Helpers (`view_helpers.py`)
- `save_planner_entries()` and `collect_planner_entries()` accept optional `enabled_slots` parameter (defaults to `MEAL_SLOTS`)
- Both iterate `enabled_slots` instead of `MEAL_SLOTS`

### Dashboard View (`views_dashboard.py`)
- Added `meal_slot__in=enabled_slot_keys` filter to `today_entries`, `upcoming_entries`, `planned_this_week_count`

### Settings Template (`settings.html`)
- Added checkbox group for each meal slot using `form.enabled_slots`
- Help text: "Uncheck a slot to hide it from the planner and dashboard"

### Planner Template (`planner.html`)
- Added dynamic `grid-template-columns` via inline style using `{{ meal_slots|length }}`
- Cook/undo forms automatically filter because `meal_slots` is now filtered in view

### Migration
- `recipes/migrations/0009_appsetting_enabled_slots.py`

### Version
- `config.yaml`: 0.1.28 → 0.1.29
- `CHANGELOG.md`: Entry added

## Verification
- `python manage.py check` — 0 issues ✅
- `python manage.py test` — 63 tests pass ✅
- `python manage.py makemigrations --check --dry-run` — No changes ✅

## Key Design Decisions
- Existing entries for disabled slots are **preserved** (not deleted) — they reappear if slot is re-enabled
- Empty `enabled_slots` (new installs / existing DBs after migration) = all slots shown
- Random auto-fill only fills visible cells (JS queries DOM, unaffected)
- Shopping list generation unaffected — hidden entries still contribute to ingredient totals

# Mission: Add meal slot enable/disable toggle to settings

## M1: Model & Data Layer | status: completed
### T1.1: Add enabled_slots to AppSetting model | agent:Worker | status: completed
- [x] S1.1.1: Add `enabled_slots` JSONField and `active_meal_slots` property to `models.py`
- [x] S1.1.2: Create Django migration

### T1.2: Update SettingsForm | agent:Worker | status: completed
- [x] S1.2.1: Add `enabled_slots` MultipleChoiceField with CheckboxSelectMultiple to `forms.py`

## M2: Backend Logic | status: completed
### T2.1: Update planner view | agent:Worker | status: completed
- [x] S2.1.1: Filter `meal_slots` in `views_planner.py` via `active_meal_slots`
- [x] S2.1.2: Pass enabled_slots to `save_planner_entries`

### T2.2: Update view_helpers | agent:Worker | status: completed
- [x] S2.2.1: Update `save_planner_entries` and `collect_planner_entries` to accept and iterate enabled_slots

### T2.3: Update dashboard view | agent:Worker | status: completed
- [x] S2.3.1: Filter today/upcoming entries in `views_dashboard.py` to only show enabled slots

## M3: Frontend | status: completed
### T3.1: Update settings template | agent:Worker | status: completed
- [x] S3.1.1: Add checkbox group to `settings.html`

### T3.2: Update planner template | agent:Worker | status: completed
- [x] S3.2.1: Make grid columns dynamic based on enabled slot count
- [x] S3.2.2: Filter cook/undo forms to only render for enabled slots

### T3.3: Update planner CSS | agent:Worker | status: completed
- [x] S3.3.1: Add inline styles for dynamic column counts

## M4: Verification | agent:Reviewer | status: in_progress
- [x] S4.1: Run `python manage.py check` — ✅ 0 issues
- [x] S4.2: Run `python manage.py test` — ✅ 63 tests pass
- [x] S4.3: Final review pass by Reviewer
- [x] S4.4: Update CHANGELOG.md and config.yaml version

# Project Context — Categories Management & Settings Tabs

## Mission
Add a dedicated "Manage Categories" page with CRUD operations and tabbed sub-navigation to the Settings section.

## Environment
- Language: Python 3 (Django)
- Runtime: Alpine Linux via Docker
- Build: `docker compose -f recipe_planner/docker-compose.yml up --build -d`
- Test: `docker exec shelfserve-dev /opt/shelfserve/venv/bin/python manage.py test`
- Django manage: `docker exec shelfserve-dev /opt/shelfserve/venv/bin/python manage.py <cmd>`
- App: http://127.0.0.1:8099/
- Venv: `/opt/shelfserve/venv/bin/python`
- App dir: `/opt/shelfserve/app/`

## Key Files
- `recipes/models.py` — `IngredientCategory` model (name, order)
- `recipes/views_ingredients.py` — ingredient management views
- `recipes/urls.py` — all URL patterns
- `recipes/templates/recipes/settings.html` — settings page (week_start, accent_color, meal_slots)
- `recipes/templates/recipes/ingredient_list.html` — ingredient management page
- `recipes/templates/recipes/base.html` — top nav with Settings link
- `recipes/static/recipes/app.css` — all app styling
- `recipes/forms.py` — SettingsForm, RecipeForm, etc.

## Plan
1. Create `views_categories.py` with CRUD views for IngredientCategory
2. Create `category_list.html` template with inline rename, reorder, delete
3. Add category URLs to `urls.py`
4. Create `_settings_tabs.html` include for sub-navigation (General | Categories | Ingredients)
5. Add tab bar to settings.html, ingredient_list.html, ingredient_edit.html, category_list.html
6. Update base.html nav highlight for settings sub-pages

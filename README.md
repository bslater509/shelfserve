# ShelfServe

ShelfServe is a Home Assistant OS add-on for storing recipes, planning meals, and generating supermarket-sorted shopping lists.

The add-on runs a Django app through Home Assistant ingress, so it opens from the Home Assistant sidebar without exposing a separate public web service.

## Features

- Store recipes with ingredients, quantities, units, notes, tags, steps, and optional images.
- Plan breakfast, lunch, and dinner recipes by week.
- Generate shopping lists from the meal plan.
- Sort shopping list items by supermarket section.
- Mark shopping list items as checked while shopping.
- Configure supermarket section order and the preferred week start day.

## Repository Layout

```text
.
|-- repository.yaml              # Home Assistant add-on repository metadata
`-- recipe_planner/
    |-- config.yaml              # ShelfServe add-on metadata
    |-- Dockerfile               # Add-on image build
    |-- run.sh                   # Container startup script
    |-- icon.png                 # Add-on icon
    |-- logo.png                 # Add-on logo
    `-- app/
        |-- manage.py
        |-- requirements.txt
        |-- shelfserve/          # Django project
        `-- recipes/             # Main Django app
```

## Install In Home Assistant

1. Open Home Assistant.
2. Go to **Settings > Add-ons > Add-on Store**.
3. Open the three-dot menu and choose **Repositories**.
4. Add this repository URL:

   ```text
   https://github.com/bslater509/shelfserve
   ```

5. Install **ShelfServe** from the add-on store.
6. Start the add-on.
7. Open **ShelfServe** from the Home Assistant sidebar or the add-on Web UI button.

## Updating The Add-On

Home Assistant only picks up repository changes after the add-on store is refreshed and the add-on image is rebuilt or updated.

For normal GitHub installs:

1. Commit and push the repository changes.
2. If the running add-on should update, bump `recipe_planner/config.yaml` `version` before pushing.
3. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
4. Open the three-dot menu and choose **Check for updates**.
5. Update or reinstall **ShelfServe**.
6. Restart the add-on.
7. Open ShelfServe through Home Assistant ingress and verify the new behavior.

If Home Assistant does not show an update, confirm the pushed commit includes a new add-on version in `recipe_planner/config.yaml`, then check for updates again.

## Local Development

Run development commands from `recipe_planner/app/`.

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv ..\..\.venv
..\..\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the Django checks and tests:

```powershell
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

Run the app locally:

```powershell
python manage.py migrate
python manage.py runserver
```

The local development server defaults to:

```text
http://127.0.0.1:8000/
```

## Container Startup

The Home Assistant add-on starts with `recipe_planner/run.sh`. It:

- Uses `/data` for persistent add-on data by default.
- Creates `/data/media` and `/data/static`.
- Runs database migrations.
- Collects static files.
- Starts Gunicorn on port `8099`.

Persistent runtime data should stay under the add-on data volume, not inside the application directory.

## Home Assistant Ingress

ShelfServe is served under a generated Home Assistant ingress path such as:

```text
/3975db7c_shelfserve/
```

Templates and application code should avoid hard-coded root-relative links like `/static/...`, `/media/...`, or `/recipes/...`. Use Django URL and static helpers so navigation, assets, media, forms, and CSRF checks continue to work through ingress.

## License

No license file is currently included.

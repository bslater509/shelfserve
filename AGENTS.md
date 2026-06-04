# AGENTS.md

## Project Overview

ShelfServe is a Home Assistant OS add-on for recipe storage, meal planning, and supermarket-sorted shopping lists. The add-on lives in `recipe_planner/` and runs a Django app from `recipe_planner/app/`.

The repository can include pre-created image assets. Home Assistant add-on store assets already exist at:

- `recipe_planner/icon.png`
- `recipe_planner/logo.png`

Keep these binary files in the repo unless replacing them intentionally.

## Important Paths

- `repository.yaml`: Home Assistant add-on repository metadata.
- `recipe_planner/config.yaml`: Add-on metadata and ingress configuration.
- `recipe_planner/Dockerfile`: Add-on image build.
- `recipe_planner/run.sh`: Container startup, migrations, static collection, and Gunicorn.
- `recipe_planner/app/shelfserve/settings.py`: Django settings.
- `recipe_planner/app/shelfserve/middleware.py`: Home Assistant ingress path handling.
- `recipe_planner/app/recipes/`: Main Django application.
- `recipe_planner/app/recipes/static/recipes/app.css`: App styling.
- `recipe_planner/app/recipes/templates/recipes/`: HTML templates.

## Home Assistant Ingress Notes

The add-on is served through Home Assistant ingress, which places the app under a generated path such as `/3975db7c_shelfserve/`. Avoid hard-coded root-relative links such as `/static/...`, `/media/...`, or `/recipes/...` in templates and application code.

Use Django helpers where possible:

- `{% url 'view_name' %}` for app navigation.
- `{% static 'recipes/app.css' %}` for static assets.
- Model file/image `.url` values for uploaded media.

If changing URL, static, or media handling, verify the page through Home Assistant ingress. A raw, unstyled HTML page usually means static assets are resolving outside the ingress path.

## Home Assistant Update Path

Always provide the user with a clear way to apply repository changes in Home Assistant. Most code, template, static asset, Dockerfile, and add-on metadata changes require rebuilding or reinstalling the add-on image before Home Assistant will run the updated code.

When handing off changes, include the relevant update path:

- Before any git push intended to update the Home Assistant add-on, bump `recipe_planner/config.yaml` `version` so Home Assistant can detect the new build.
- If the add-on was installed from GitHub, commit and push the repo changes, then in Home Assistant go to **Settings > Add-ons > Add-on Store**, open the three-dot menu, choose **Check for updates**, then update or reinstall **ShelfServe**.
- If Home Assistant does not show an update, confirm the pushed commit includes a bumped `recipe_planner/config.yaml` `version`, check for updates again, then rebuild/update the add-on.
- If testing locally with the add-on repository mounted or copied into Home Assistant, reload the add-on store, rebuild/reinstall the add-on, and restart **ShelfServe**.
- After updating, use **Restart** on the add-on page and open the Web UI through Home Assistant ingress to verify the running add-on reflects the repo changes.

Do not leave the user with only local verification steps when the fix is intended for Home Assistant.

## Development Commands

Run commands from `recipe_planner/app/` unless noted otherwise.

```powershell
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

For add-on container behavior, inspect `recipe_planner/run.sh`. It runs:

```sh
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear
gunicorn shelfserve.wsgi:application --bind 0.0.0.0:${SHELFSERVE_PORT}
```

## Coding Guidelines

- Before analyzing the repository or making changes, run `git status --short` and `git pull` so the local workspace is up to date. If the working tree already has local changes, inspect them first and avoid overwriting user work.
- After making any intended repo changes, commit and git push them so Home Assistant can update from the remote repository. For Home Assistant add-on updates, bump `recipe_planner/config.yaml` `version` before pushing.
- Preserve the existing Django structure and simple server-rendered templates.
- Keep Home Assistant ingress compatibility in mind for every link, form action, static asset, and media URL.
- Store persistent runtime data under the add-on `/data` volume through `SHELFSERVE_DATA_DIR`; do not write persistent user data into the app directory.
- Keep changes focused. Do not refactor unrelated models, templates, or add-on metadata while fixing ingress or UI issues.
- Use ASCII in source files unless an existing file clearly uses another character set.

## Verification Checklist

Before handing off changes:

- Run `python manage.py check`.
- Run targeted Django tests when behavior changes.
- Confirm generated HTML uses the Home Assistant ingress path for navigation and assets.
- For add-on metadata changes, confirm `recipe_planner/config.yaml` remains valid YAML.

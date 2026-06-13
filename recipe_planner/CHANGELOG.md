# Changelog

## 0.1.31

- Overhaul recipe import: richer URL scraping (ingredient groups, dietary/cuisine/cooking tags, total-time fallback, author prefix), improved raw text parser, per-request ingredient cache, ingredient normalization, source URL duplicate detection, loading spinner, inline error display, and specific exception handling.
- Add `ImportForm` with URL format and non-empty validation.
- Add `group_name` field to `RecipeIngredient` model, displayed in the recipe editor and detail pages, with cook mode group support.

## 0.1.30

- Add searchable list of supported recipe websites to the import page, showing all 583 domains the built-in `recipe-scrapers` library supports.

## 0.1.29

- Add per-slot meal type toggle in Settings to enable or disable breakfast, lunch, or dinner slots globally. Disabled slots are hidden from the planner page and dashboard; existing entries are preserved and reappear if the slot is re-enabled.

## 0.1.28

- Fix recipe ingredient import parsing for BBC Food metric/imperial alternatives (e.g. `450g/1lb Italian sausages` now correctly extracts 450g).

## 0.1.27

- The main ShelfServe UI now respects your system's dark mode preference (`prefers-color-scheme: dark`). The topbar, cards, panels, buttons, form fields, modals, planner grid, and shopping lists all adapt with theme-appropriate colors and contrast.
- Dark-mode page background (#121212), card panels (#1e1e1e), and softer border colors (#3c4043) work across Dashboard, Recipes, Pantry, Planner, Supermarkets, and Shopping lists.
- The cook mode overlay retains its independent dark/light toggle — system dark mode does not lock it to dark.

## 0.1.26

- Fix ingredient category preservation on restock: existing categories are no longer overwritten by the shopping-list section name.
- Gracefully handle unknown unit values in pantry and shopping-list operations by falling back to Item instead of crashing.
- Add `steps` prefetch to recipe detail page to eliminate an N+1 SQL query.
- Clean up unused imports across all view files and register remaining models in the admin interface.
- Document that `undo_meal_cooked` intentionally leaves `last_cooked_at` unchanged.
- Add targeted test coverage for multi-recipe pantry deduction, unit fallback, restock category preservation, zero-quantity handling, and regeneration edge cases.
- Fix dashboard checked-items counter regression — ensures the annotation matches its name by counting checked (completed) items rather than unchecked ones.

## 0.1.25

- Refactor recipe, planner, pantry, supermarket, and shopping-list views into focused maintenance modules while keeping existing URLs and behavior unchanged.
- Move page-specific JavaScript and larger planner, shopping-list, and recipe-detail styles into dedicated static assets loaded through Home Assistant ingress-aware URLs.

## 0.1.24

- Move internal view helper logic into a dedicated helper module to make the recipe views easier to maintain.
- Keep existing recipe, planner, pantry, supermarket, and shopping-list behavior unchanged.

## 0.1.23

- Add reusable weekly planner templates that can be saved from the current planner grid.
- Allow saved templates to be previewed on any planner week before saving them as the active meal plan.
- Add in-planner template deletion controls.

## 0.1.22

- Refresh an existing supermarket/week shopping list instead of creating duplicate lists.
- Show pantry coverage on generated shopping-list items and allow checked shopping items to restock pantry quantities.
- Add low-stock thresholds for pantry items and surface low-stock pantry stock on the dashboard.
- Add recipe source URL, prep time, cook time, favorite, and last-cooked metadata.
- Improve recipe import metadata and raw-text title/serving detection.
- Add recipe library filters for favorites, pantry-friendly recipes, never-cooked recipes, and recipes missing images.
- Add optional notes to planned meal slots.

## 0.1.21

- Add recipe library sorting by title, newest, recently updated, or servings.
- Add quick filtering to pantry stock and shopping lists.
- Remember the shopping-list hide-checked preference per list and keep progress counts live while ticking items.
- Link the dashboard's active shopping-list count directly to the first list with items remaining.

## 0.1.20

- Add pantry tracking for ingredients already on hand.
- Subtract matching pantry stock from generated and regenerated shopping lists without changing pantry quantities.
- Add planner controls for marking meals as cooked and undoing cooked meals, updating pantry stock only when requested.

## 0.1.19

- Refresh the main ShelfServe interface with clearer navigation, active page states, and improved mobile wrapping.
- Improve the dashboard with current-week meal counts, recent list progress, upcoming meals, and faster action links.
- Add recipe tag filtering alongside search and polish recipe library empty states and cards.
- Improve planner controls with a Today shortcut, clearer shopping-list generation action, and more efficient recipe picker data loading.
- Improve shopping lists with a progress meter, per-section item counts, cleaner item metadata, and a hide-checked toggle.
- Clean up everyday form pages and fix visible separator encoding issues.

## 0.1.18

- Add shopping list regeneration that preserves checked generated items while refreshing quantities from the meal plan.
- Keep custom shopping list items separate from generated recipe items so one-off purchases survive regeneration.
- Add edit and delete controls for shopping list items.
- Show shopping list completion counts on list pages and the dashboard.
- Link from the planner to existing shopping lists for the selected week.

## 0.1.17

- Fix unicode fraction parsing for imported ingredients.
- Harden imported recipe image downloads with response size, content type, image format, and Pillow validation checks.
- Clean up imported image preview URL handling for Home Assistant ingress.
- Normalize recipe editor and supermarket aisle controls to stable ASCII-safe source text.

## 0.1.16

- Add dynamic Servings Stepper to Recipe detail page, allowing real-time client-side scaling of ingredient quantities.
- Implement Decimal Step toggle next to servings stepper to enable 0.5-unit increments.
- Add premium distraction-free fullscreen "Cook Mode" checklist overlay for kitchen use, hiding standard page navigation.
- Support progress tracking with checked-step dimming and automatic completion status updates.
- Embed active inline cooking timers synchronized perfectly between the Cook Mode checklist and the main recipe detail view.
- Include a collapsible scaled Ingredients Drawer within Cook Mode for quick quantity verification.
- Feature custom high-contrast Kitchen Night Mode (Dark Theme toggle) within Cook Mode overlay, persisting choice to local storage.

## 0.1.15

- Overhaul weekly planner page with a fully interactive, responsive grid layout.
- Replace simple select dropdowns with a visual overlay modal supporting search and tags.
- Add quick action planning tools, including Random Auto-fill, Clear Week, and Clear Day.
- Implement GET-parameter-driven "Copy Previous Week" draft-generation flow for previewing and editing before saving.
- Enhance planner aesthetics with premium Outfit Google Typography, glassmorphism visual feedback, transition animations, and custom inline SVGs.
- Optimize HTML payload by rendering the list of cookbook recipes exactly once inside the visual selection modal rather than repeating options for each slot.

## 0.1.14

- Migrate recipe instructions from a single plain-text field to a structured database-backed `RecipeStep` table.
- Support adding, removing, and reordering instructions and ingredients dynamically in the editor with Up/Down buttons.
- Automatically extract step durations (e.g. "Bake for 30 minutes") during URL scraping and raw text imports.
- Implement interactive countdown cooking timers on the recipe detail page, utilizing the browser's native Web Audio API to synthesize alarm beeps.

## 0.1.13

- Add Recipe Importer supporting scraping from web URLs (using `recipe-scrapers`) and copy-pasting raw recipe text.
- Implement Smart Rule-Based Parser to automatically extract ingredient names, notes, quantities, and units.
- Support pre-populating and editing imported recipe data before saving, including downloading and previewing recipe images.

## 0.1.12

- Add dynamic autocomplete suggestions for ingredient names and aisles in recipe creation/edit forms.
- Implement interactive AJAX toggling for shopping list items with optimistic updates.
- Support adding custom one-off items directly to any shopping list, grouped into their correct supermarket aisle.

## 0.1.11

- Add new premium glow-morphic style logo and icon for ShelfServe server and Home Assistant add-on dashboard.

## 0.1.10

- Replace basic text area supermarket aisle editor with interactive row-based editor supporting reordering, addition, and deletion.
- Add ability to modify the supermarket name directly on the detail page.

## 0.1.9

- Save aisle order changes in place for the selected supermarket without recreating other supermarket aisle rows.

## 0.1.8

- Fix Home Assistant ingress form submissions when the browser sends an opaque `Origin: null` header.

## 0.1.2

- Publish prebuilt multi-architecture container images through GitHub Actions.
- Configure Home Assistant to install the published image instead of building locally.

## 0.1.0

- Initial Home Assistant add-on version.
- Added recipe storage, weekly planning, supermarkets, and shopping checklists.

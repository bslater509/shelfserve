# Changelog

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

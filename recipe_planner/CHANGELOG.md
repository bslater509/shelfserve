# Changelog

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

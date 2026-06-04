# ShelfServe Documentation

ShelfServe runs inside Home Assistant through Ingress. Home Assistant handles access to the web UI, and the add-on stores its database and uploaded images in `/data`.

## First Run

1. Install and start the add-on.
2. Open the web UI from Home Assistant.
3. Create at least one supermarket and enter its aisle order.
4. Add recipes with structured ingredients.
5. Plan recipes into breakfast, lunch, or dinner slots.
6. Generate a shopping list for a week and supermarket.

## Backups

The SQLite database is stored at `/data/recipes.sqlite3`. Uploaded recipe images are stored under `/data/media`. Home Assistant add-on backups include this persistent data.

## Notes

This first version does not create Home Assistant entities or calendar events. It is a self-contained web application presented inside Home Assistant.

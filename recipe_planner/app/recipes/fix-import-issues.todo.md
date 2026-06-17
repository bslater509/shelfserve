# Recipe Import Issues - Fix Checklist

## Issue 1: simplyrecipes.com — `instructions()` crashes silently

**Observed:** All 17 simplyrecipes.com URLs tested (banana bread, hummus, chicken noodle soup, pizza dough, lasagna, garlic bread, etc.) are imported with a title, ingredients, and metadata but **zero steps**. The recipe detail page shows "No steps added for this recipe."

**Root cause:** `recipe-scrapers` v14.x throws `AttributeError: 'NoneType' object has no attribute 'ol'` when calling `scraper.instructions()` or `scraper.instructions_list()` on simplyrecipes.com pages. The error occurs inside the scraper's HTML parser because the page's instruction markup uses a structure the scraper doesn't expect (e.g., a different `<ol>` class name or a `<div>` wrapper).

In `parser.py:parse_recipe_url()` (lines 518-537), exceptions from `scraper.instructions()` are caught by a bare `except Exception`, and the fallback `scraper.instructions_list()` at line 535 also fails with the same error. The `except Exception` at line 536 silently swallows the error, leaving `raw_steps` empty, which propagates to an empty `steps` list.

**Fix options:**

- **Option A (upstream fix):** Update `recipe-scrapers` to a version that handles simplyrecipes.com correctly. Check the latest release for simplyrecipes fix.
- **Option B (manual DOM parsing):** In `parser.py`, in the fallback branch (lines 534-537), instead of only trying `instructions_list()`, access `scraper.soup` directly to extract instructions from the page HTML:
  ```python
  if not raw_steps:
      try:
          raw_steps = scraper.instructions_list()
      except Exception:
          pass
      if not raw_steps:
          try:
              ol = scraper.soup.find('ol', class_='recipe__instructions')
              if ol:
                  raw_steps = [li.get_text(strip=True) for li in ol.find_all('li') if li.get_text(strip=True)]
          except Exception:
              pass
  ```
- **Option C (log and skip):** Log a warning with the URL and error details so the issue is visible in logs, even if steps can't be recovered.

**Files to modify:** `recipe_planner/app/recipes/parser.py` (lines 518-537)

---

## Issue 2: loveandlemons.com — certain pages import with zero ingredients

**Observed:** 4 loveandlemons.com recipes (Baked Sweet Potato, Best Vegan Chili, Brussels Sprout Salad Avocado Toasts, Cauliflower Rice Kimchi Bowls) are imported with a title, steps, and metadata but **zero ingredients**. The recipe detail page shows an empty ingredient section.

**Root cause:** These loveandlemons pages have redirects (e.g., `/stuffed-sweet-potato/` → `/stuffed-sweet-potatoes/`). After following the redirect, `recipe-scrapers` returns `scraper.ingredients()` as an empty list `[]` and `scraper.ingredient_groups()` returns one group with empty `ingredients = []`. The scraper successfully gets all other fields (title, instructions, image) but fails to parse ingredients from the redirected page's schema.

In `parser.py:parse_recipe_url()`, lines 551-569:
- `groups` is obtained successfully (not None) but each group has empty `ingredients`
- The `else` branch (line 566) is never reached because `groups` is truthy
- The for-loop at line 559 iterates over 0 items, so no ingredients are appended

**Fix options:**

- **Option A:** Resolve redirects before scraping: use `requests.head()` to get the canonical URL first, then scrape that URL.
- **Option B:** If `ingredient_groups()` returns groups with all-empty ingredients, fall through to `scraper.ingredients()` as a backup:
  ```python
  if groups:
      all_empty = True
      for group in groups:
          if group.ingredients:
              all_empty = False
              break
      if all_empty:
          groups = None  # fall through to plain ingredients
  ```
- **Option C:** Before saving, check if ingredients list is empty and log a warning. Consider not saving the recipe at all if it has zero ingredients (or saving with an error message).

**Files to modify:** `recipe_planner/app/recipes/parser.py` (lines 551-569)

---

## Issue 3: Multi-numbered steps are concatenated into a single long step

**Observed:** 10+ recipes (from foodnetwork.com, halfbakedharvest.com, damndelicious.net, delish.com, etc.) have steps of 800-1700+ characters that contain 3-6 numbered sub-steps all combined. For example:
```
"1. Preheat the oven to 450° F. 2. On a baking sheet, toss the broccoli with olive oil. 3. Roast until tender."
```

**Root cause:** In `parser.py:parse_recipe_url()`, lines 529-531, the scraper's `instructions()` output is split only by newlines:
```python
raw_steps = [step.strip() for step in str(instructions or "").splitlines() if step.strip()]
```
Many sites return instructions as a single text block with inline numbering but no newlines (e.g., "1. Preheat...2. Add..."). The newline-only split produces a single step containing all numbered sub-steps.

When `instructions_list()` is available (line 535), it correctly returns individual steps. But for sites where both `instructions()` and `instructions_list()` are unavailable or return the same unsplit text, this issue occurs.

**Fix options:**

- **Option A:** After splitting by newlines, apply a secondary split on numbered patterns for any step exceeding a threshold (e.g., 300 chars):
  ```python
  def split_numbered_steps(text):
      parts = re.split(r'(?:^|\s)(?=\d+[.)]\s)', text)
      return [p.strip() for p in parts if p.strip()]
  ```
- **Option B:** First try `instructions_list()`. If it returns a single long string or fails, split `instructions()` by both newlines AND numbered patterns.
- **Option C:** Apply the numbered split unconditionally after the newline split, so "1. Preheat...2. Bake..." becomes two separate steps.

**Files to modify:** `recipe_planner/app/recipes/parser.py` (around lines 529-546)

---

## Issue 4: delish.com — `instructions()` returns empty for certain recipes

**Observed:** The `Alfredo Sauce` recipe from delish.com imports with ingredients and metadata but **zero steps**. `scraper.instructions()` returns an empty string `""` and `instructions_list()` returns `[]`.

**Root cause:** `recipe-scrapers` cannot parse the instruction markup on this specific delish.com recipe page. The recipe content is loaded dynamically or uses a non-standard `<div>` structure that the scraper doesn't handle. This may be a page-specific formatting issue or a general delish.com scraper limitation.

Unlike simplyrecipes.com (Issue 1), this doesn't crash with an exception — it silently returns empty data.

**Fix options:**

- **Option A:** Check `recipe-scrapers` issue tracker for delish.com support status. If a newer version fixes it, upgrade.
- **Option B:** Add logging when `raw_steps` is empty after all attempts, noting the URL so the issue can be tracked.
- **Option C:** For the specific case where instructions are empty but ingredients are present, try extracting steps from the raw HTML using `scraper.soup`:
  ```python
  if not raw_steps:
      import re
      # Try to extract numbered list items from the page body
      body = str(scraper.soup)
      step_match = re.search(r'<div[^>]*class="[^"]*directions[^"]*"[^>]*>(.*?)</div>', body, re.DOTALL)
      if step_match:
          lis = re.findall(r'<li[^>]*>(.*?)</li>', step_match.group(1), re.DOTALL)
          raw_steps = [re.sub(r'<[^>]+>', '', li).strip() for li in lis if re.sub(r'<[^>]+>', '', li).strip()]
  ```
- **Option D:** Log a warning and skip saving the recipe if both ingredients AND steps are empty, but allow saving if one of them has data (current behavior is fine, just add visibility).

**Files to modify:** `recipe_planner/app/recipes/parser.py` (around lines 518-546)

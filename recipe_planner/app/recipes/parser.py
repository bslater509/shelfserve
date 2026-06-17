import io
import json
import logging
import re
import uuid
import urllib.request
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from recipe_scrapers import get_supported_urls, scrape_me
from recipe_scrapers._exceptions import WebsiteNotImplementedError

from recipes.models import Ingredient, Unit
from recipes.services import display_quantity, load_normalization_cache, normalise_ingredient_name, normalise_name


logger = logging.getLogger(__name__)
MAX_RECIPE_IMAGE_BYTES = 5 * 1024 * 1024

RECIPE_IMAGE_FORMATS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}

UNICODE_FRACTIONS = {
    "\u00bd": Decimal("0.5"),
    "\u2153": Decimal("0.3333333333"),
    "\u2154": Decimal("0.6666666667"),
    "\u00bc": Decimal("0.25"),
    "\u00be": Decimal("0.75"),
    "\u215b": Decimal("0.125"),
    "\u215c": Decimal("0.375"),
    "\u215d": Decimal("0.625"),
    "\u215e": Decimal("0.875"),
}
UNICODE_FRACTION_PATTERN = "".join(re.escape(char) for char in UNICODE_FRACTIONS)

SERVING_PATTERNS = (
    "to taste",
    "for garnish",
    "for serving",
    "to serve",
    "for garnish:",
    "for decoration",
    "for dusting",
    "garnish with",
)

UNIT_MAPPING = {
    "g": Unit.GRAM,
    "gram": Unit.GRAM,
    "grams": Unit.GRAM,
    "kg": Unit.KILOGRAM,
    "kilogram": Unit.KILOGRAM,
    "kilograms": Unit.KILOGRAM,
    "ml": Unit.MILLILITRE,
    "milliliter": Unit.MILLILITRE,
    "milliliters": Unit.MILLILITRE,
    "millilitre": Unit.MILLILITRE,
    "millilitres": Unit.MILLILITRE,
    "l": Unit.LITRE,
    "liter": Unit.LITRE,
    "liters": Unit.LITRE,
    "litre": Unit.LITRE,
    "litres": Unit.LITRE,
    "tsp": Unit.TEASPOON,
    "tsp.": Unit.TEASPOON,
    "teaspoon": Unit.TEASPOON,
    "teaspoons": Unit.TEASPOON,
    "tbsp": Unit.TABLESPOON,
    "tbsp.": Unit.TABLESPOON,
    "tablespoon": Unit.TABLESPOON,
    "tablespoons": Unit.TABLESPOON,
    "cup": Unit.CUP,
    "cups": Unit.CUP,
    "clove": Unit.CLOVE,
    "cloves": Unit.CLOVE,
    "pinch": Unit.PINCH,
    "pinches": Unit.PINCH,
    "slice": Unit.SLICE,
    "slices": Unit.SLICE,
    "piece": Unit.PIECE,
    "pieces": Unit.PIECE,
    "head": Unit.HEAD,
    "heads": Unit.HEAD,
    "bunch": Unit.BUNCH,
    "bunches": Unit.BUNCH,
    "stalk": Unit.STALK,
    "stalks": Unit.STALK,
    "pack": Unit.PACK,
    "packs": Unit.PACK,
    "package": Unit.PACK,
    "packages": Unit.PACK,
    "box": Unit.PACK,
    "boxes": Unit.PACK,
    "can": Unit.PACK,
    "cans": Unit.PACK,
    "tin": Unit.PACK,
    "tins": Unit.PACK,
    "bag": Unit.PACK,
    "bags": Unit.PACK,
    "carton": Unit.PACK,
    "cartons": Unit.PACK,
    "bottle": Unit.PACK,
    "bottles": Unit.PACK,
    "jar": Unit.PACK,
    "jars": Unit.PACK,
    "rasher": Unit.SLICE,
    "rashers": Unit.SLICE,
    "lb": Unit.POUND,
    "lbs": Unit.POUND,
    "pound": Unit.POUND,
    "pounds": Unit.POUND,
    "oz": Unit.OUNCE,
    "ounce": Unit.OUNCE,
    "ounces": Unit.OUNCE,
}

NON_STANDARD_UNITS = {}

UNIT_ADJECTIVES = {"heaped", "heaping", "level", "rounded", "scant", "generous"}

ARTICLES = {"a", "an"}

CONTAINER_WORDS = {
    "can", "cans", "tin", "tins", "jar", "jars",
    "bottle", "bottles", "carton", "cartons",
    "pot", "pots", "pack", "packs", "bag", "bags", "box", "boxes",
}

INSTRUCTION_SEPARATORS = (
    " plus a little ",
    " plus ",
    " extra ",
    " for ",
)

INSTRUCTION_TRAILING_WORDS = frozenset({
    "frying", "cooking", "serving", "garnish", "decoration",
    "dusting", "dipping", "drizzling", "basting", "glazing",
    "sprinkling", "coating", "mixing", "stirring", "whisking",
})


def download_recipe_image(image_url):
    """Download a verified recipe image and return its path inside MEDIA_ROOT."""
    if not image_url:
        return ""

    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw_content_type = response.headers.get("Content-Type")
            content_type = response.headers.get_content_type() if raw_content_type else ""
            if content_type and not content_type.startswith("image/"):
                logger.warning("Recipe image download skipped due to content type: %s", content_type)
                return ""
            image_data = response.read(MAX_RECIPE_IMAGE_BYTES + 1)

        if len(image_data) > MAX_RECIPE_IMAGE_BYTES:
            logger.warning("Recipe image download skipped because it exceeded %s bytes", MAX_RECIPE_IMAGE_BYTES)
            return ""

        try:
            with Image.open(io.BytesIO(image_data)) as image:
                image.verify()
                image_format = image.format
        except UnidentifiedImageError:
            logger.warning("Recipe image download skipped because the response was not a valid image")
            return ""

        ext = RECIPE_IMAGE_FORMATS.get(image_format)
        if not ext:
            logger.warning("Recipe image download skipped due to unsupported image format: %s", image_format)
            return ""

        media_recipes_dir = Path(settings.MEDIA_ROOT) / "recipes"
        media_recipes_dir.mkdir(parents=True, exist_ok=True)

        filename = f"imported_{uuid.uuid4().hex}.{ext}"
        file_path = media_recipes_dir / filename
        file_path.write_bytes(image_data)
        return f"recipes/{filename}"
    except Exception as exc:
        logger.warning("Failed to download recipe image from %s: %s", image_url, exc)
        return ""


def parse_servings(yields):
    """Robustly parse servings/yields count into an integer."""
    if yields is None:
        return 4
    if isinstance(yields, (int, float)):
        return max(1, int(yields))
    if yields == "":
        return 4
    match = re.search(r"\d+", str(yields))
    if match:
        return max(1, int(match.group()))
    return 4


def scraper_minutes(scraper, method_name):
    method = getattr(scraper, method_name, None)
    if not method:
        return None
    try:
        value = method()
    except Exception:
        return None
    if value in (None, ""):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        value = int(match.group())
    return max(1, value) if value else None


def _load_ingredient_cache():
    """Pre-load all existing ingredients into a dict keyed by normalised name."""
    ingredients = Ingredient.objects.select_related("category").values(
        "name", "category__name"
    ).all()
    cache = {}
    for entry in ingredients:
        key = normalise_name(entry["name"]).lower()
        if key not in cache:
            cache[key] = entry["category__name"] or ""
    return cache


def _ingredient_category(name, cache):
    """Look up ingredient category from pre-loaded cache by normalised name."""
    if not name:
        return ""
    key = normalise_name(name).lower()
    return cache.get(key, "")


def _is_serving_instruction(name, note):
    """Check if a parsed ingredient line is actually a serving/garnish instruction."""
    name_lower = (name or "").lower()
    note_lower = (note or "").lower()
    for pattern in SERVING_PATTERNS:
        if pattern in name_lower or pattern in note_lower:
            return True
    return False


def _extract_quantity(text):
    """Extract leading quantity from text, return (Decimal, remaining_text) or (None, text)."""
    rest = text.strip()

    mixed_unicode = re.match(rf"^(\d+)\s*([{UNICODE_FRACTION_PATTERN}])", rest)
    if mixed_unicode:
        whole = int(mixed_unicode.group(1))
        frac_val = UNICODE_FRACTIONS[mixed_unicode.group(2)]
        return (Decimal(whole) + frac_val, rest[mixed_unicode.end():].strip())

    unicode_frac = re.match(rf"^([{UNICODE_FRACTION_PATTERN}])", rest)
    if unicode_frac:
        return (UNICODE_FRACTIONS[unicode_frac.group(1)], rest[unicode_frac.end():].strip())

    mixed_frac = re.match(r"^(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)", rest)
    if mixed_frac:
        whole = int(mixed_frac.group(1))
        num = int(mixed_frac.group(2))
        den = int(mixed_frac.group(3))
        return (Decimal(whole) + (Decimal(num) / Decimal(den)), rest[mixed_frac.end():].strip())

    frac = re.match(r"^(\d+)\s*/\s*(\d+)", rest)
    if frac:
        num = int(frac.group(1))
        den = int(frac.group(2))
        return (Decimal(num) / Decimal(den), rest[frac.end():].strip())

    dec = re.match(r"^(\d+(?:\.\d+)?)", rest)
    if dec:
        return (Decimal(dec.group(1)), rest[dec.end():].strip())

    return (None, text)


def parse_ingredient_line(line, ingredient_cache=None, normalization_cache=None):
    """Parse a single ingredient string into structured fields."""
    line = line.strip()
    if not line:
        return None

    quantity = Decimal("1.0")
    rest = line

    parsed_quantity, rest = _extract_quantity(rest)
    if parsed_quantity is not None:
        quantity = parsed_quantity

    if rest:
        range_match = re.match(r"^[\-\u2013\u2014]\s*\d+\s*", rest)
        if range_match:
            rest = rest[range_match.end():]
        else:
            to_range = re.match(r"^to\s+\d+\s*", rest)
            if to_range:
                rest = rest[to_range.end():]

    if rest.lower().startswith("of "):
        rest = rest[3:].strip()
    elif rest.lower().startswith("x ") or rest.lower().startswith("- "):
        rest = rest[2:].strip()
        if rest:
            x_quantity, x_rest = _extract_quantity(rest)
            if x_quantity is not None:
                x_words = x_rest.split()
                container_follows = False
                if len(x_words) >= 2:
                    candidate = x_words[1].lower().rstrip(".")
                    if candidate in CONTAINER_WORDS:
                        container_follows = True
                if quantity == Decimal("1.0") or not container_follows:
                    quantity = x_quantity
                    rest = x_rest
                    range_match = re.match(r"^[\-\u2013\u2014]\s*\d+\s*", rest)
                    if range_match:
                        rest = rest[range_match.end():]
                    if rest.lower().startswith("of "):
                        rest = rest[3:].strip()

    if rest:
        re_qty, re_rest = _extract_quantity(rest)
        if re_qty is not None:
            quantity = re_qty
            rest = re_rest

    note = ""
    paren_match = re.search(r"\(([^)]+)\)", rest)
    if paren_match:
        note = paren_match.group(1).strip()
        rest = rest.replace(paren_match.group(0), "").strip()

    if "," in rest:
        parts = rest.split(",", 1)
        rest = parts[0].strip()
        comma_note = parts[1].strip()
        note = f"{note}, {comma_note}" if note else comma_note

    words = rest.split()
    unit = Unit.ITEM
    name = rest

    if words:
        first_word = words[0].lower().rstrip(".")
        first_word_clean = re.sub(r"[^\w]", "", first_word)

        if first_word in UNIT_ADJECTIVES and len(words) > 1:
            second_word = words[1].lower().rstrip(".")
            second_word_clean = re.sub(r"[^\w]", "", second_word)
            if second_word in UNIT_MAPPING:
                unit = UNIT_MAPPING[second_word]
                name = " ".join(words[2:])
            elif second_word_clean in UNIT_MAPPING:
                unit = UNIT_MAPPING[second_word_clean]
                name = " ".join(words[2:])
            elif "/" in second_word:
                slash_prefix = second_word.split("/")[0]
                if slash_prefix in UNIT_MAPPING:
                    unit = UNIT_MAPPING[slash_prefix]
                    name = " ".join(words[2:])

        if name == rest:
            if first_word in UNIT_MAPPING:
                unit = UNIT_MAPPING[first_word]
                name = " ".join(words[1:])
            elif first_word_clean in UNIT_MAPPING:
                unit = UNIT_MAPPING[first_word_clean]
                name = " ".join(words[1:])
            elif first_word in ARTICLES and len(words) >= 2:
                if len(words) == 2:
                    name = words[1]
                else:
                    second_word = words[1].lower().rstrip(".")
                    second_word_clean = re.sub(r"[^\w]", "", second_word)
                    if second_word in UNIT_MAPPING:
                        unit = UNIT_MAPPING[second_word]
                        name = " ".join(words[2:])
                    elif second_word_clean in UNIT_MAPPING:
                        unit = UNIT_MAPPING[second_word_clean]
                        name = " ".join(words[2:])
                    elif "/" in second_word:
                        slash_prefix = second_word.split("/")[0]
                        if slash_prefix in UNIT_MAPPING:
                            unit = UNIT_MAPPING[slash_prefix]
                            name = " ".join(words[2:])
                    else:
                        name = " ".join(words[1:])
            elif "/" in first_word:
                slash_prefix = first_word.split("/")[0]
                if slash_prefix in UNIT_MAPPING:
                    unit = UNIT_MAPPING[slash_prefix]
                    name = " ".join(words[1:])
                name = " ".join(words[1:])

        if name.lower().startswith("of "):
            name = name[3:].strip()

    if name:
        _name = name
        for sep in INSTRUCTION_SEPARATORS:
            if sep in _name.lower():
                idx = _name.lower().rfind(sep)
                trailing = _name[idx:].strip()
                trailing_words = set(re.findall(r'\w+', trailing.lower()))
                if trailing_words & INSTRUCTION_TRAILING_WORDS:
                    _name = _name[:idx].strip()
                    if trailing:
                        note = f"{note}, {trailing}" if note else trailing
                    break
        name = _name

    if name.endswith(")") and "(" not in name:
        name = name[:-1].strip()
    if name.endswith("("):
        name = name[:-1].strip()
    if name.startswith(")") and "(" not in name:
        name = name[1:].strip()
    if note.endswith(")") and "(" not in note:
        note = note[:-1].strip()
    if note.endswith("("):
        note = note[:-1].strip()

    if _is_serving_instruction(name, note):
        return None

    if name:
        name = normalise_ingredient_name(name, normalization_cache)

    if ingredient_cache is not None:
        category = _ingredient_category(name, ingredient_cache)
    else:
        category = _ingredient_category(name, _load_ingredient_cache())

    quantity = quantity.quantize(Decimal("0.01"))

    return {
        "name": name,
        "quantity": display_quantity(quantity),
        "unit": unit,
        "note": note,
        "category": category,
        "group_name": "",
    }


def extract_step_duration(text):
    """Look for time mentions like '15 minutes' or '1 hour' and return minutes."""
    if not text:
        return None
    hr_min_match = re.search(
        r"\b(\d+)\s*(?:hour|hr)s?\s*(?:and\s*)?(\d+)\s*(?:min|minute)s?\b",
        text,
        re.IGNORECASE,
    )
    if hr_min_match:
        return int(hr_min_match.group(1)) * 60 + int(hr_min_match.group(2))

    hr_match = re.search(r"\b(\d+)\s*(?:hour|hr)s?\b", text, re.IGNORECASE)
    if hr_match:
        return int(hr_match.group(1)) * 60

    min_match = re.search(r"\b(\d+)\s*(?:min|minute)s?\b", text, re.IGNORECASE)
    if min_match:
        return int(min_match.group(1))

    return None


_supported_websites = None


def get_supported_websites():
    global _supported_websites
    if _supported_websites is None:
        _supported_websites = sorted(get_supported_urls())
    return _supported_websites


def _scraper_tag_list(scraper, *method_names):
    """Collect string tags from multiple scraper methods, return deduplicated list."""
    tags = set()
    for name in method_names:
        method = getattr(scraper, name, None)
        if not method:
            continue
        try:
            value = method()
        except (NotImplementedError, Exception):
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    tags.add(item.lower().strip())
        elif isinstance(value, str):
            for part in value.split(","):
                part = part.strip().lower()
                if part:
                    tags.add(part)
    return sorted(tags)


def _fallback_parse_ingredients(soup, ingredient_cache, normalization_cache):
    """Extract ingredients from HTML soup when recipe-scrapers returns nothing."""
    ingredients = []
    text_lines = []

    # Strategy 1: JSON-LD recipeIngredient
    for script in soup.select("script[type=\"application/ld+json\"]"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                ings = data.get("recipeIngredient") or []
                if isinstance(ings, list) and ings:
                    text_lines = ings
                    break
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        ings = item.get("recipeIngredient") or []
                        if isinstance(ings, list) and ings:
                            text_lines = ings
                            break
                if text_lines:
                    break
        except (json.JSONDecodeError, Exception):
            continue

    # Strategy 2: WPRM ingredient items (WordPress Recipe Maker plugin)
    if not text_lines:
        for li in soup.select(".wprm-recipe-ingredients-container li.wprm-recipe-ingredient, .wprm-recipe-ingredient"):
            text = li.get_text(separator=" ", strip=True)
            if text:
                text_lines.append(text)

    # Strategy 3: Generic li.ingredient or [class*=ingredient] li
    if not text_lines:
        for li in soup.select("li.ingredient, [class*=\"ingredient\"] li"):
            text = li.get_text(separator=" ", strip=True)
            if text:
                text_lines.append(text)

    for line in text_lines:
        parsed = parse_ingredient_line(line, ingredient_cache, normalization_cache)
        if parsed:
            ingredients.append(parsed)

    return ingredients


def _fallback_parse_steps(soup):
    """Extract steps from HTML soup when recipe-scrapers returns nothing."""
    raw_steps = []

    # Strategy 1: JSON-LD recipeInstructions
    for script in soup.select("script[type=\"application/ld+json\"]"):
        try:
            data = json.loads(script.string)
            items = None
            if isinstance(data, dict):
                items = data.get("recipeInstructions")
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "recipeInstructions" in item:
                        items = item["recipeInstructions"]
                        break
            if isinstance(items, list):
                for inst in items:
                    if isinstance(inst, dict):
                        text = inst.get("text") or inst.get("name") or ""
                    elif isinstance(inst, str):
                        text = inst
                    else:
                        continue
                    text = str(text).strip()
                    if text:
                        raw_steps.append(text)
                if raw_steps:
                    break
        except (json.JSONDecodeError, Exception):
            continue

    # Strategy 2: WPRM instruction items
    if not raw_steps:
        for li in soup.select(".wprm-recipe-instructions-container li, .wprm-recipe-instruction"):
            text = li.get_text(separator=" ", strip=True)
            if text:
                raw_steps.append(text)

    # Strategy 3: Common instruction list patterns
    if not raw_steps:
        for ol_class in ("recipe__instructions", "directions__list", "recipe-directions__list", "instructions", "steps"):
            ol = soup.find("ol", class_=ol_class)
            if ol:
                raw_steps = [li.get_text(separator=" ", strip=True) for li in ol.find_all("li") if li.get_text(separator=" ", strip=True)]
                break
        if not raw_steps:
            for ol in soup.find_all("ol"):
                steps_from_ol = [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]
                if len(steps_from_ol) >= 2:
                    raw_steps = steps_from_ol
                    break

    return raw_steps


def parse_recipe_url(url):
    """Scrape a recipe URL using recipe-scrapers."""
    scraper = scrape_me(url)

    title = scraper.title()
    servings = parse_servings(scraper.yields())

    raw_steps = []
    try:
        instructions = scraper.instructions()
        if isinstance(instructions, list):
            for item in instructions:
                if isinstance(item, dict):
                    text = item.get("text", "").strip()
                else:
                    text = str(item).strip()
                if text:
                    raw_steps.append(text)
        else:
            raw_steps = [step.strip() for step in str(instructions or "").splitlines() if step.strip()]
    except Exception:
        pass

    if not raw_steps:
        try:
            raw_steps = scraper.instructions_list()
        except Exception:
            pass

    if not raw_steps:
        try:
            for ol_class in ("recipe__instructions", "directions__list", "recipe-directions__list", "instructions"):
                ol = scraper.soup.find("ol", class_=ol_class)
                if ol:
                    raw_steps = [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]
                    break
            if not raw_steps:
                for ol in scraper.soup.find_all("ol"):
                    steps_from_ol = [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]
                    if len(steps_from_ol) >= 2:
                        raw_steps = steps_from_ol
                        break
        except Exception:
            pass

    if not raw_steps and hasattr(scraper, "soup"):
        raw_steps = _fallback_parse_steps(scraper.soup)

    if not raw_steps:
        logger.warning("No steps extracted from %s", url)

    split_steps = []
    for step in raw_steps:
        if len(step) > 300:
            parts = re.split(r"(?:^|\s)(?=\d+[.)]\s)", step)
            for part in parts:
                stripped = part.strip()
                if stripped:
                    split_steps.append(stripped)
        else:
            split_steps.append(step)
    raw_steps = split_steps

    steps = []
    for step in raw_steps:
        steps.append(
            {
                "text": step,
                "duration_minutes": extract_step_duration(step),
            }
        )

    ingredient_cache = _load_ingredient_cache()
    normalization_cache = load_normalization_cache()
    ingredients = []
    try:
        groups = scraper.ingredient_groups()
    except Exception:
        groups = None

    if groups:
        for group in groups:
            group_purpose = group.purpose.strip() if group.purpose else ""
            for line in group.ingredients:
                parsed = parse_ingredient_line(line, ingredient_cache, normalization_cache)
                if parsed:
                    if group_purpose:
                        parsed["group_name"] = group_purpose
                    ingredients.append(parsed)
        if not ingredients:
            for line in scraper.ingredients():
                parsed = parse_ingredient_line(line, ingredient_cache, normalization_cache)
                if parsed:
                    ingredients.append(parsed)
    else:
        for line in scraper.ingredients():
            parsed = parse_ingredient_line(line, ingredient_cache, normalization_cache)
            if parsed:
                ingredients.append(parsed)

    if not ingredients and hasattr(scraper, "soup"):
        ingredients = _fallback_parse_ingredients(scraper.soup, ingredient_cache, normalization_cache)

    if not ingredients:
        logger.warning("No ingredients extracted from %s", url)

    tags = []
    try:
        keywords = scraper.keywords()
        if isinstance(keywords, list):
            tags.extend(keywords)
        elif isinstance(keywords, str):
            tags.extend([tag.strip() for tag in keywords.split(",") if tag.strip()])
    except Exception:
        pass

    category = scraper.category()
    if isinstance(category, str):
        tags.extend([tag.strip() for tag in category.split(",") if tag.strip()])

    extra_tags = _scraper_tag_list(
        scraper, "dietary_restrictions", "cuisine", "cooking_method"
    )
    tags.extend(extra_tags)

    clean_tags = sorted({tag.lower().strip() for tag in tags if tag.strip()})[:5]

    prep_minutes = scraper_minutes(scraper, "prep_time")
    cook_minutes = scraper_minutes(scraper, "cook_time")
    if prep_minutes is None and cook_minutes is None:
        total = scraper_minutes(scraper, "total_time")
        if total is not None:
            prep_minutes = total

    source_url = url

    return {
        "title": title,
        "servings": servings,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "steps": steps,
        "ingredients": ingredients,
        "tags_list": clean_tags,
        "source_url": source_url,
        "image_path": download_recipe_image(scraper.image()),
    }


TEXT_SECTION_HEADERS = {
    "ingredients", "ingredient", "ingredients list", "ingredient list",
    "shopping list",
    "instructions", "instruction", "directions", "direction",
    "steps", "step", "method", "preparation",
    "assembly", "to serve", "garnish",
    "marinade", "marinate", "sauce", "for the sauce",
    "for the marinade", "for the dressing", "for the filling",
    "for the dough", "for the crust", "for the topping",
}

TEXT_NOTE_HEADERS = {"note", "notes", "tip", "tips", "chef's tip", "chefs tip", "chef tip"}


def parse_recipe_text(text):
    """Parse raw copy-pasted recipe text into ingredients and instructions."""
    lines = [line.strip() for line in text.splitlines()]

    title = "Imported Recipe"
    servings = 4
    ingredients = []
    steps_list = []
    state = 1
    content_lines = [line for line in lines if line]
    first_content_line = content_lines[0] if content_lines else ""
    skip_title_line = False
    if first_content_line:
        first_clean = re.sub(r"[^\w\s]", "", first_content_line.lower()).strip()
        first_is_for = re.match(r"^for\s+the\s+", first_clean)
        if first_clean not in TEXT_SECTION_HEADERS and not first_is_for and not re.match(r"^\d", first_content_line):
            title = first_content_line
            skip_title_line = True

    ingredient_cache = _load_ingredient_cache()
    normalization_cache = load_normalization_cache()

    for line in lines:
        if not line:
            continue
        if skip_title_line and line == first_content_line:
            skip_title_line = False
            continue

        line_lower = line.lower()
        line_clean = re.sub(r"[^\w\s]", "", line_lower).strip()

        servings_match = re.search(
            r"\b(?:serves|servings|yield|yields|makes?)\s*:?\s*(\d+)\b",
            line_lower,
        )
        if servings_match:
            servings = max(1, int(servings_match.group(1)))
            continue

        if line_clean in TEXT_NOTE_HEADERS:
            state = 3
            continue

        if line_clean in TEXT_SECTION_HEADERS:
            if "ingredient" in line_clean or "shopping" in line_clean:
                state = 1
            else:
                state = 2
            continue

        if re.match(r"^for\s+the\s+", line_clean) and state != 2:
            state = 1
            continue

        if state == 3:
            continue

        if state == 1:
            parsed = parse_ingredient_line(line, ingredient_cache, normalization_cache)
            if parsed:
                ingredients.append(parsed)
        elif state == 2:
            clean = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            steps_list.append(clean if clean else line)

    steps = []
    for line in steps_list:
        steps.append(
            {
                "text": line,
                "duration_minutes": extract_step_duration(line),
            }
        )

    return {
        "title": title,
        "servings": servings,
        "prep_minutes": None,
        "cook_minutes": None,
        "steps": steps,
        "ingredients": ingredients,
        "tags_list": ["imported"],
        "source_url": "",
        "image_path": "",
    }

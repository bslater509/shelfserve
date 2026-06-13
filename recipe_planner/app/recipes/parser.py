import io
import logging
import re
import uuid
import urllib.request
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from recipe_scrapers import get_supported_urls, scrape_me

from recipes.models import Ingredient, Unit


logger = logging.getLogger(__name__)
MAX_RECIPE_IMAGE_BYTES = 5 * 1024 * 1024

# Cache for ingredient category lookups to avoid N+1 queries during batch parsing
_ingredient_category_cache: dict[str, str] = {}


def _ingredient_category(name):
    """Get ingredient category with module-level cache to avoid repeated DB hits."""
    if name not in _ingredient_category_cache:
        existing = Ingredient.objects.filter(name__iexact=name).only("category").first()
        _ingredient_category_cache[name] = existing.category if existing else ""
    return _ingredient_category_cache[name]
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
}

NON_STANDARD_UNITS = {
    "cup": "cup",
    "cups": "cup",
    "clove": "clove",
    "cloves": "clove",
    "pinch": "pinch",
    "pinches": "pinch",
    "slice": "slice",
    "slices": "slice",
    "piece": "piece",
    "pieces": "piece",
    "head": "head",
    "heads": "head",
    "bunch": "bunch",
    "bunches": "bunch",
    "stalk": "stalk",
    "stalks": "stalk",
    "can": "can",
    "cans": "can",
    "tin": "tin",
    "tins": "tin",
    "bottle": "bottle",
    "bottles": "bottle",
    "jar": "jar",
    "jars": "jar",
}


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
    if not yields:
        return 4
    if isinstance(yields, (int, float)):
        return max(1, int(yields))
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


def parse_ingredient_line(line):
    """Parse a single ingredient string into structured fields."""
    line = line.strip()
    if not line:
        return None

    quantity = Decimal("1.0")
    rest = line

    mixed_unicode = re.match(rf"^(\d+)\s*([{UNICODE_FRACTION_PATTERN}])", rest)
    if mixed_unicode:
        whole = int(mixed_unicode.group(1))
        frac_val = UNICODE_FRACTIONS[mixed_unicode.group(2)]
        quantity = Decimal(whole) + frac_val
        rest = rest[mixed_unicode.end():].strip()
    else:
        unicode_frac = re.match(rf"^([{UNICODE_FRACTION_PATTERN}])", rest)
        if unicode_frac:
            quantity = UNICODE_FRACTIONS[unicode_frac.group(1)]
            rest = rest[unicode_frac.end():].strip()
        else:
            mixed_frac = re.match(r"^(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)", rest)
            if mixed_frac:
                whole = int(mixed_frac.group(1))
                num = int(mixed_frac.group(2))
                den = int(mixed_frac.group(3))
                quantity = Decimal(whole) + (Decimal(num) / Decimal(den))
                rest = rest[mixed_frac.end():].strip()
            else:
                frac = re.match(r"^(\d+)\s*/\s*(\d+)", rest)
                if frac:
                    num = int(frac.group(1))
                    den = int(frac.group(2))
                    quantity = Decimal(num) / Decimal(den)
                    rest = rest[frac.end():].strip()
                else:
                    dec = re.match(r"^(\d+(?:\.\d+)?)", rest)
                    if dec:
                        quantity = Decimal(dec.group(1))
                        rest = rest[dec.end():].strip()

    if rest.lower().startswith("of "):
        rest = rest[3:].strip()
    elif rest.lower().startswith("x ") or rest.lower().startswith("- "):
        rest = rest[2:].strip()

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

        if first_word in UNIT_MAPPING:
            unit = UNIT_MAPPING[first_word]
            name = " ".join(words[1:])
        elif first_word_clean in UNIT_MAPPING:
            unit = UNIT_MAPPING[first_word_clean]
            name = " ".join(words[1:])
        elif "/" in first_word:
            # Handle patterns like "450g/1lb Italian sausages" where the first
            # word contains a metric/imperial alternative separated by "/".
            slash_prefix = first_word.split("/")[0]
            if slash_prefix in UNIT_MAPPING:
                unit = UNIT_MAPPING[slash_prefix]
                name = " ".join(words[1:])
            elif slash_prefix in NON_STANDARD_UNITS:
                unit = Unit.ITEM
                non_std = NON_STANDARD_UNITS[slash_prefix]
                name = " ".join(words[1:])
                note = f"{non_std}, {note}" if note else non_std
        elif first_word in NON_STANDARD_UNITS:
            unit = Unit.ITEM
            non_std = NON_STANDARD_UNITS[first_word]
            name = " ".join(words[1:])
            note = f"{non_std}, {note}" if note else non_std
        elif first_word_clean in NON_STANDARD_UNITS:
            unit = Unit.ITEM
            non_std = NON_STANDARD_UNITS[first_word_clean]
            name = " ".join(words[1:])
            note = f"{non_std}, {note}" if note else non_std

        if name.lower().startswith("of "):
            name = name[3:].strip()

    category = _ingredient_category(name) if name else ""

    quantity = quantity.quantize(Decimal("0.01"))

    return {
        "name": name,
        "quantity": str(quantity),
        "unit": unit,
        "note": note,
        "category": category,
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


def parse_recipe_url(url):
    """Scrape a recipe URL using recipe-scrapers."""
    scraper = scrape_me(url)

    title = scraper.title()
    servings = parse_servings(scraper.yields())

    instructions = scraper.instructions()
    raw_steps = []
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

    steps = []
    for step in raw_steps:
        steps.append(
            {
                "text": step,
                "duration_minutes": extract_step_duration(step),
            }
        )

    ingredients = []
    for line in scraper.ingredients():
        parsed = parse_ingredient_line(line)
        if parsed:
            ingredients.append(parsed)

    tags = []
    keywords = scraper.keywords()
    if isinstance(keywords, list):
        tags.extend(keywords)
    elif isinstance(keywords, str):
        tags.extend([tag.strip() for tag in keywords.split(",") if tag.strip()])

    category = scraper.category()
    if isinstance(category, str):
        tags.extend([tag.strip() for tag in category.split(",") if tag.strip()])

    clean_tags = sorted({tag.lower().strip() for tag in tags if tag.strip()})[:5]

    return {
        "title": title,
        "servings": servings,
        "prep_minutes": scraper_minutes(scraper, "prep_time"),
        "cook_minutes": scraper_minutes(scraper, "cook_time"),
        "steps": steps,
        "ingredients": ingredients,
        "tags_list": clean_tags,
        "source_url": url,
        "image_path": download_recipe_image(scraper.image()),
    }


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
    possible_headings = {
        "ingredients",
        "ingredient",
        "ingredients list",
        "ingredient list",
        "shopping list",
        "instructions",
        "instruction",
        "directions",
        "direction",
        "steps",
        "step",
        "method",
        "preparation",
    }
    skip_title_line = False
    if first_content_line:
        first_clean = re.sub(r"[^\w\s]", "", first_content_line.lower()).strip()
        if first_clean not in possible_headings and not re.match(r"^\d", first_content_line):
            title = first_content_line
            skip_title_line = True

    for line in lines:
        if not line:
            continue
        if skip_title_line and line == first_content_line:
            skip_title_line = False
            continue

        line_lower = line.lower()
        line_clean = re.sub(r"[^\w\s]", "", line_lower).strip()
        servings_match = re.search(r"\b(?:serves|servings|yield|yields)\s*:?\s*(\d+)\b", line_lower)
        if servings_match:
            servings = max(1, int(servings_match.group(1)))
            continue
        if line_clean in ["ingredients", "ingredient", "ingredients list", "ingredient list", "shopping list"]:
            state = 1
            continue
        if line_clean in ["instructions", "instruction", "directions", "direction", "steps", "step", "method", "preparation"]:
            state = 2
            continue

        if state == 1:
            parsed = parse_ingredient_line(line)
            if parsed:
                ingredients.append(parsed)
        elif state == 2:
            steps_list.append(line)

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

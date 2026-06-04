import re
import uuid
import urllib.request
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from recipe_scrapers import scrape_me
from recipes.models import Unit, Ingredient

# Map unicode fraction characters to Decimal values
UNICODE_FRACTIONS = {
    '½': 0.5, '⅓': 0.33, '⅔': 0.67, '¼': 0.25, '¾': 0.75, 
    '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875
}

# Standard unit mapping to Unit model choices
UNIT_MAPPING = {
    'g': Unit.GRAM,
    'gram': Unit.GRAM,
    'grams': Unit.GRAM,
    
    'kg': Unit.KILOGRAM,
    'kilogram': Unit.KILOGRAM,
    'kilograms': Unit.KILOGRAM,
    
    'ml': Unit.MILLILITRE,
    'milliliter': Unit.MILLILITRE,
    'milliliters': Unit.MILLILITRE,
    'millilitre': Unit.MILLILITRE,
    'millilitres': Unit.MILLILITRE,
    
    'l': Unit.LITRE,
    'liter': Unit.LITRE,
    'liters': Unit.LITRE,
    'litre': Unit.LITRE,
    'litres': Unit.LITRE,
    
    'tsp': Unit.TEASPOON,
    'tsp.': Unit.TEASPOON,
    'teaspoon': Unit.TEASPOON,
    'teaspoons': Unit.TEASPOON,
    
    'tbsp': Unit.TABLESPOON,
    'tbsp.': Unit.TABLESPOON,
    'tablespoon': Unit.TABLESPOON,
    'tablespoons': Unit.TABLESPOON,
    
    'pack': Unit.PACK,
    'packs': Unit.PACK,
    'package': Unit.PACK,
    'packages': Unit.PACK,
    'box': Unit.PACK,
    'boxes': Unit.PACK,
    'can': Unit.PACK,
    'cans': Unit.PACK,
    'tin': Unit.PACK,
    'tins': Unit.PACK,
    'bag': Unit.PACK,
    'bags': Unit.PACK,
    'carton': Unit.PACK,
    'cartons': Unit.PACK,
    'bottle': Unit.PACK,
    'bottles': Unit.PACK,
    'jar': Unit.PACK,
    'jars': Unit.PACK,
}

# Common non-standard units that map to Unit.ITEM but should have unit name stored in note
NON_STANDARD_UNITS = {
    'cup': 'cup', 'cups': 'cup',
    'clove': 'clove', 'cloves': 'clove',
    'pinch': 'pinch', 'pinches': 'pinch',
    'slice': 'slice', 'slices': 'slice',
    'piece': 'piece', 'pieces': 'piece',
    'head': 'head', 'heads': 'head',
    'bunch': 'bunch', 'bunches': 'bunch',
    'stalk': 'stalk', 'stalks': 'stalk',
    'can': 'can', 'cans': 'can',
    'tin': 'tin', 'tins': 'tin',
    'bottle': 'bottle', 'bottles': 'bottle',
    'jar': 'jar', 'jars': 'jar',
}

def download_recipe_image(image_url):
    """Downloads recipe image and returns the relative path inside MEDIA_ROOT."""
    if not image_url:
        return ""
    try:
        req = urllib.request.Request(
            image_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            image_data = response.read()
        
        media_recipes_dir = Path(settings.MEDIA_ROOT) / "recipes"
        media_recipes_dir.mkdir(parents=True, exist_ok=True)
        
        ext = "jpg"
        if ".png" in image_url.lower():
            ext = "png"
        elif ".webp" in image_url.lower():
            ext = "webp"
            
        filename = f"imported_{uuid.uuid4().hex}.{ext}"
        file_path = media_recipes_dir / filename
        file_path.write_bytes(image_data)
        return f"recipes/{filename}"
    except Exception as e:
        # Ignore and log failures, recipe will just have no image
        print(f"Failed to download image {image_url}: {e}")
        return ""

def parse_servings(yields):
    """Robustly parse servings/yields count into an integer."""
    if not yields:
        return 4
    if isinstance(yields, (int, float)):
        return max(1, int(yields))
    match = re.search(r'\d+', str(yields))
    if match:
        return max(1, int(match.group()))
    return 4

def parse_ingredient_line(line):
    """Parses a single ingredient string into structured fields using a Smart Rule-Based Parser."""
    line = line.strip()
    if not line:
        return None
        
    quantity = Decimal('1.0')
    rest = line
    
    # 1. Extract Quantity at the start of string
    # Check mixed unicode fractions e.g. "1 ½" or "1½"
    mixed_unicode = re.match(r'^(\d+)\s*([½⅓⅔¼¾⅛⅜⅝⅞])', rest)
    if mixed_unicode:
        whole = int(mixed_unicode.group(1))
        frac_val = UNICODE_FRACTIONS[mixed_unicode.group(2)]
        quantity = Decimal(str(whole + frac_val))
        rest = rest[mixed_unicode.end():].strip()
    else:
        # Check unicode fraction alone e.g. "½"
        unicode_frac = re.match(r'^([½⅓⅔¼¾⅛⅜⅝⅞])', rest)
        if unicode_frac:
            quantity = Decimal(str(UNICODE_FRACTIONS[unicode_frac.group(1)]))
            rest = rest[unicode_frac.end():].strip()
        else:
            # Check mixed standard fraction e.g. "1 1/2" or "1-1/2"
            mixed_frac = re.match(r'^(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)', rest)
            if mixed_frac:
                whole = int(mixed_frac.group(1))
                num = int(mixed_frac.group(2))
                den = int(mixed_frac.group(3))
                quantity = Decimal(str(whole + num / den))
                rest = rest[mixed_frac.end():].strip()
            else:
                # Check standard fraction alone e.g. "1/2"
                frac = re.match(r'^(\d+)\s*/\s*(\d+)', rest)
                if frac:
                    num = int(frac.group(1))
                    den = int(frac.group(2))
                    quantity = Decimal(str(num / den))
                    rest = rest[frac.end():].strip()
                else:
                    # Check decimal/integer
                    dec = re.match(r'^(\d+(?:\.\d+)?)', rest)
                    if dec:
                        quantity = Decimal(dec.group(1))
                        rest = rest[dec.end():].strip()
                        
    # Clean leading 'x' or '-' or 'of' if quantity was extracted
    if rest.lower().startswith('of '):
        rest = rest[3:].strip()
    elif rest.lower().startswith('x ') or rest.lower().startswith('- '):
        rest = rest[2:].strip()
        
    # 2. Extract Notes (parentheses or commas)
    note = ""
    # Extract parentheses
    paren_match = re.search(r'\(([^)]+)\)', rest)
    if paren_match:
        note = paren_match.group(1).strip()
        rest = rest.replace(paren_match.group(0), "").strip()
        
    # Extract comma note
    if "," in rest:
        parts = rest.split(",", 1)
        rest = parts[0].strip()
        comma_note = parts[1].strip()
        if note:
            note = f"{note}, {comma_note}"
        else:
            note = comma_note
            
    # 3. Extract Unit & Name
    words = rest.split()
    unit = Unit.ITEM
    name = rest
    
    if words:
        first_word = words[0].lower().rstrip('.')
        first_word_clean = re.sub(r'[^\w]', '', first_word)
        
        # Check standard units
        if first_word in UNIT_MAPPING:
            unit = UNIT_MAPPING[first_word]
            name = " ".join(words[1:])
        elif first_word_clean in UNIT_MAPPING:
            unit = UNIT_MAPPING[first_word_clean]
            name = " ".join(words[1:])
        # Check non-standard units (which map to Unit.ITEM, unit stored in note)
        elif first_word in NON_STANDARD_UNITS:
            unit = Unit.ITEM
            non_std = NON_STANDARD_UNITS[first_word]
            name = " ".join(words[1:])
            if note:
                note = f"{non_std}, {note}"
            else:
                note = non_std
        elif first_word_clean in NON_STANDARD_UNITS:
            unit = Unit.ITEM
            non_std = NON_STANDARD_UNITS[first_word_clean]
            name = " ".join(words[1:])
            if note:
                note = f"{non_std}, {note}"
            else:
                note = non_std

        # Clean trailing/leading connector words (e.g. "of")
        if name.lower().startswith("of "):
            name = name[3:].strip()
            
    # 4. Lookup category from existing database ingredients
    category = ""
    if name:
        existing = Ingredient.objects.filter(name__iexact=name).first()
        if existing:
            category = existing.category
            
    # Round quantity to 2 decimals
    quantity = quantity.quantize(Decimal('0.01'))
    
    return {
        "name": name,
        "quantity": str(quantity),
        "unit": unit,
        "note": note,
        "category": category,
    }

def extract_step_duration(text):
    """Uses regex to look for time mentions like '15 minutes' or '1 hour' and returns duration in minutes."""
    if not text:
        return None
    # 1. Hour + minute pattern: e.g., "1 hour 30 minutes" or "1 hr 30 mins"
    hr_min_match = re.search(
        r'\b(\d+)\s*(?:hour|hr)s?\s*(?:and\s*)?(\d+)\s*(?:min|minute)s?\b', 
        text, 
        re.IGNORECASE
    )
    if hr_min_match:
        return int(hr_min_match.group(1)) * 60 + int(hr_min_match.group(2))
        
    # 2. Hours only pattern: e.g., "1 hour" or "2 hrs"
    hr_match = re.search(r'\b(\d+)\s*(?:hour|hr)s?\b', text, re.IGNORECASE)
    if hr_match:
        return int(hr_match.group(1)) * 60
        
    # 3. Minutes only pattern: e.g., "15 minutes" or "10 mins"
    min_match = re.search(r'\b(\d+)\s*(?:min|minute)s?\b', text, re.IGNORECASE)
    if min_match:
        return int(min_match.group(1))
        
    return None


def parse_recipe_url(url):
    """Scrapes a recipe URL using recipe-scrapers library."""
    scraper = scrape_me(url)
    
    title = scraper.title()
    servings = parse_servings(scraper.yields())
    
    # Process instructions
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
        # Split by newlines if it's a single string
        raw_steps = [s.strip() for s in str(instructions or "").splitlines() if s.strip()]
        
    steps = []
    for s in raw_steps:
        duration = extract_step_duration(s)
        steps.append({
            "text": s,
            "duration_minutes": duration
        })
        
    # Process ingredients
    raw_ingredients = scraper.ingredients()
    ingredients = []
    for line in raw_ingredients:
        parsed = parse_ingredient_line(line)
        if parsed:
            ingredients.append(parsed)
            
    # Download image
    image_rel_path = download_recipe_image(scraper.image())
    
    # Extract tags
    tags = []
    keywords = scraper.keywords()
    if isinstance(keywords, list):
        tags.extend(keywords)
    elif isinstance(keywords, str):
        tags.extend([t.strip() for t in keywords.split(",") if t.strip()])
        
    category = scraper.category()
    if isinstance(category, str):
        tags.extend([t.strip() for t in category.split(",") if t.strip()])
        
    clean_tags = sorted(list(set([t.lower().strip() for t in tags if t.strip()])))[:5]
    
    return {
        "title": title,
        "servings": servings,
        "steps": steps,
        "ingredients": ingredients,
        "tags_list": clean_tags,
        "image_path": image_rel_path,
    }

def parse_recipe_text(text):
    """Parses raw text copy-paste input, splitting it into ingredients and instructions."""
    lines = [line.strip() for line in text.splitlines()]
    
    title = "Imported Recipe"
    servings = 4
    ingredients = []
    steps_list = []
    
    # We default to state=1 (Ingredients) as they usually come first
    state = 1
    
    for line in lines:
        if not line:
            continue
            
        line_lower = line.lower()
        # Header check: match clean whole words to avoid sub-string hits like "Mix ingredients"
        line_clean = re.sub(r'[^\w\s]', '', line_lower).strip()
        if line_clean in ["ingredients", "ingredient", "ingredients list", "ingredient list", "shopping list"]:
            state = 1
            continue
        elif line_clean in ["instructions", "instruction", "directions", "direction", "steps", "step", "method", "preparation"]:
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
        duration = extract_step_duration(line)
        steps.append({
            "text": line,
            "duration_minutes": duration
        })
    
    return {
        "title": title,
        "servings": servings,
        "steps": steps,
        "ingredients": ingredients,
        "tags_list": ["imported"],
        "image_path": "",
    }

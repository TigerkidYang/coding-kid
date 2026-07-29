import re


def slugify(text: str) -> str:
    """Make a URL slug: lowercase, hyphens, alnum only."""
    # BUG: keeps underscores and does not collapse repeated hyphens/spaces
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9_\s-]", "", text)
    return text.replace(" ", "-")

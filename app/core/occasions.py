"""Occasion rules (PRD 12.3).

Each occasion maps to a formality range on the 1-5 scale we already extract for
every garment (1 = very casual, 5 = very formal). This lets Stage 1 remove
unsuitable items with a plain rule, before the language model runs — no AI call
needed to know a gym tee does not belong at a wedding.
"""

# occasion -> (min_formality, max_formality), inclusive
OCCASIONS: dict[str, tuple[int, int]] = {
    "gym": (1, 2),
    "casual": (1, 3),
    "office": (3, 4),
    "party": (3, 5),
    "wedding": (4, 5),
    "formal": (4, 5),
}


def formality_range(occasion: str | None) -> tuple[int, int] | None:
    """The allowed formality range for an occasion, or None if not a known one."""
    if not occasion:
        return None
    return OCCASIONS.get(occasion.lower())

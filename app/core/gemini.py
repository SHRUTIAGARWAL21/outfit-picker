"""The one place that talks to Gemini.

It does exactly one job: hand it the bytes of a garment photo, get back a
structured description as JSON. Everything else (downloading the image, saving
the result, retrying) belongs to the worker.

Two design choices worth knowing:

1. We ask Gemini for STRICT JSON that matches `GarmentAttributes`. The SDK
   validates the model's answer against that schema for us, so the worker
   receives a real Python object, not a blob of text to parse and pray over.

2. We translate Gemini's errors into our own TransientError / PermanentError
   (PRD 6.3), so the worker can decide "retry" vs "give up" without knowing
   anything about Gemini's specific error types.
"""

from pydantic import BaseModel, Field

from app.config import settings
from app.core.errors import PermanentError, TransientError

# Bump this whenever the fields below change. It is stored on each garment row
# so we can later find and re-extract rows that used an older format (PRD 8.2).
SCHEMA_VERSION = 1


class GarmentAttributes(BaseModel):
    """The description we want back for every garment.

    Some fields are not read yet (temperature range, rain suitability, formality).
    We extract them now anyway, because PRD 12.2 and 12.3 say the schema must
    already carry them — so weather and occasion filters can be switched on later
    with no re-extraction of the whole wardrobe.
    """

    is_garment: bool = Field(
        description="True only if the photo actually shows a wearable clothing item."
    )
    category: str = Field(
        description="One of: top, bottom, dress, outerwear, footwear, accessory, other."
    )
    subcategory: str = Field(description="Specific type, e.g. t-shirt, chinos, blazer, sneakers.")
    primary_color: str = Field(description="The main colour, in plain words, e.g. navy blue.")
    secondary_colors: list[str] = Field(
        default_factory=list, description="Other notable colours, if any."
    )
    pattern: str = Field(description="solid, striped, checked, floral, graphic, or other.")
    material: str = Field(description="Best guess of the fabric, e.g. cotton, denim, wool.")
    formality: int = Field(
        ge=1, le=5, description="1 = very casual (gym), 5 = very formal (black tie)."
    )
    seasons: list[str] = Field(
        default_factory=list,
        description="Any of: spring, summer, autumn, winter — when the item suits.",
    )
    min_temp_c: int = Field(description="Lowest comfortable temperature in Celsius.")
    max_temp_c: int = Field(description="Highest comfortable temperature in Celsius.")
    rain_suitable: bool = Field(description="True if the item is fine to wear in the rain.")
    description: str = Field(description="One short sentence describing the item.")
    notes: str = Field(
        default="", description="If is_garment is false, say briefly what the photo shows instead."
    )


_PROMPT = (
    "You are a fashion cataloguer. Look at this single clothing item and fill in "
    "the structured fields. Judge colour, fabric and formality from what you see. "
    "If the photo does not clearly show one wearable garment (for example it is a "
    "person, a room, a blurry mess, or several items at once), set is_garment to "
    "false and explain in notes."
)

# The client is built once, on first use, not at import time. That keeps a bad
# or missing key from breaking every import of the app; the failure shows up only
# when a worker actually tries to use it.
_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai  # imported lazily so the web app need not load it

        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# Gemini HTTP status codes that mean "try again later" rather than "this will
# never work". Everything else is treated as permanent.
_TRANSIENT_CODES = {429, 500, 502, 503, 504}


def _generate(contents, response_schema):
    """The shared plumbing for every Gemini call: send `contents`, force a JSON
    answer that matches `response_schema`, and translate Gemini's errors into our
    TransientError / PermanentError. Returns the parsed schema object.
    """
    from google.genai import types
    from google.genai import errors as genai_errors

    client = _get_client()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                # We only want a JSON answer, never tool calls — turning this off
                # keeps a noisy SDK warning out of the logs.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except genai_errors.APIError as exc:
        # A real answer from Gemini's servers, with a status code we can classify.
        code = getattr(exc, "code", None)
        if code in _TRANSIENT_CODES:
            raise TransientError(f"Gemini {code}: {exc}") from exc
        raise PermanentError(f"Gemini rejected the request ({code}): {exc}") from exc
    except Exception as exc:
        # Network blip, timeout, DNS — no status code reached us. Worth a retry.
        raise TransientError(f"Could not reach Gemini: {exc}") from exc

    parsed = response.parsed
    if parsed is None:
        # The model answered but produced nothing usable — often a safety block.
        # One retry is cheap; if it keeps happening the caller gives up.
        raise TransientError("Gemini returned no structured result.")
    return parsed


def extract_attributes(image_bytes: bytes, mime_type: str) -> GarmentAttributes:
    """Send one image to Gemini and return its structured description.

    Raises TransientError for problems worth retrying, PermanentError otherwise.
    """
    from google.genai import types

    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    return _generate([part, _PROMPT], GarmentAttributes)


# --- Avatar profile (base image) -------------------------------------------


class AvatarProfile(BaseModel):
    """The styling facts read from the user's full-body base photo (PRD 4.2)."""

    is_full_body: bool = Field(
        description="True only if the photo clearly shows one whole person, head to feet."
    )
    body_shape: str = Field(description="e.g. rectangle, triangle, inverted triangle, hourglass, oval.")
    build: str = Field(description="Overall build, e.g. slim, average, athletic, curvy, broad.")
    skin_undertone: str = Field(description="warm, cool, or neutral.")
    hair_color: str = Field(description="The hair colour in plain words.")
    eye_color: str = Field(description="The eye colour, or 'unknown' if not visible.")
    notes: str = Field(
        default="", description="If is_full_body is false, say briefly what the photo shows instead."
    )


_AVATAR_PROMPT = (
    "You are building a styling profile from a person's full-body photo. Read the "
    "body shape, overall build, skin undertone, hair colour and eye colour. If the "
    "image is not a clear, single, head-to-toe photo of one person, set "
    "is_full_body to false and explain in notes."
)


def extract_avatar_profile(image_bytes: bytes, mime_type: str) -> AvatarProfile:
    """Read the base photo and return the styling profile. Same error rules as
    garment extraction: TransientError to retry, PermanentError to give up."""
    from google.genai import types

    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    return _generate([part, _AVATAR_PROMPT], AvatarProfile)


# --- Recommendation ranking (Step 5) ---------------------------------------


class OutfitPick(BaseModel):
    """One outfit the stylist proposes."""

    garment_ids: list[str] = Field(
        description="The ids of the garments in this outfit, copied exactly from the catalog."
    )
    reason: str = Field(description="One short sentence: why this outfit suits the request.")


class OutfitRanking(BaseModel):
    """The full ranked answer: best outfit first."""

    outfits: list[OutfitPick]


def rank_outfits(prompt_text: str, garments: list[dict], count: int) -> list[OutfitPick]:
    """Ask Gemini to build ranked outfits from the given wardrobe, as text.

    `garments` is a list of {"id": str, "attributes": {...}} dicts — only the
    candidates that passed the hard filter. The model must reuse those ids exactly.
    """
    # Build a compact one-line-per-garment catalogue. Sending text (not images)
    # is the whole point of Step 5 — it is cheap and inspectable (PRD 10.1).
    lines = []
    for g in garments:
        a = g.get("attributes") or {}
        lines.append(
            f"id={g['id']} | {a.get('category', '?')}/{a.get('subcategory', '?')} | "
            f"colour={a.get('primary_color', '?')} | formality={a.get('formality', '?')}/5 | "
            f"seasons={','.join(a.get('seasons', []) or []) or '?'} | {a.get('description', '')}"
        )
    catalogue = "\n".join(lines)

    instruction = (
        "You are a personal stylist. The user owns exactly this wardrobe:\n\n"
        f"{catalogue}\n\n"
        f'The user asks: "{prompt_text}"\n\n'
        f"Compose up to {count} complete, wearable outfits using ONLY the garment "
        "ids above. Every outfit must make sense to wear together (at least a top "
        "and a bottom, or a single dress, plus optional layers, shoes and "
        "accessories). Never invent an id. Rank the outfits best first, and give "
        "each a short one-sentence reason tied to the user's request."
    )
    return _generate([instruction], OutfitRanking).outfits

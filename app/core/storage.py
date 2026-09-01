"""Cloudinary setup — our image storage.

Importing this module configures the Cloudinary SDK once, from our settings.
Any code that needs Cloudinary imports from here, so the credentials are read
in exactly one place (same pattern as the database engine and Redis client).

`secure=True` makes Cloudinary hand back https:// URLs.
"""

import io
import time

import cloudinary
import cloudinary.uploader
import cloudinary.utils

from app.config import settings

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)


def garment_folder(user_id: str) -> str:
    """Each user's garment uploads live in their own folder. Also lets us later
    confirm an uploaded file really belongs to the user who claims it."""
    return f"garments/{user_id}"


def avatar_folder(user_id: str) -> str:
    """Each user's avatar (base photo) lives in their own folder."""
    return f"avatars/{user_id}"


def _sign_upload_to(folder: str) -> dict:
    """Create a short-lived 'authorization slip' for a direct browser upload into
    `folder`.

    The signature is a fingerprint of (the upload parameters + our API secret).
    Only someone holding the secret can produce it, and the secret never leaves
    the server. The browser sends these fields to Cloudinary along with the file;
    Cloudinary recomputes the signature and accepts the upload only if it matches.
    """
    timestamp = int(time.time())

    # Exactly the parameters the browser must also send. Cloudinary signs these.
    params_to_sign = {"timestamp": timestamp, "folder": folder}
    signature = cloudinary.utils.api_sign_request(params_to_sign, settings.cloudinary_api_secret)

    return {
        "cloud_name": settings.cloudinary_cloud_name,
        "api_key": settings.cloudinary_api_key,
        "timestamp": timestamp,
        "folder": folder,
        "signature": signature,
        "upload_url": f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload",
    }


def sign_upload(user_id: str) -> dict:
    """A signed slip to upload one garment image into this user's garment folder."""
    return _sign_upload_to(garment_folder(user_id))


def sign_avatar_upload(user_id: str) -> dict:
    """A signed slip to upload the base photo into this user's avatar folder."""
    return _sign_upload_to(avatar_folder(user_id))


def render_folder(user_id: str) -> str:
    """Each user's rendered outfit images live in their own folder."""
    return f"renders/{user_id}"


def upload_render(user_id: str, outfit_id: str, image_bytes: bytes) -> tuple[str, str]:
    """Save a rendered outfit image (raw bytes from the AI) into our own storage.

    We copy every generated image into Cloudinary rather than keeping a provider
    URL, so the interest section never has to regenerate it (PRD 10.8). Returns
    (public_id, secure_url).
    """
    result = cloudinary.uploader.upload(
        io.BytesIO(image_bytes),
        folder=render_folder(user_id),
        public_id=str(outfit_id),  # one render per outfit; re-render overwrites
        overwrite=True,
    )
    return result["public_id"], result["secure_url"]

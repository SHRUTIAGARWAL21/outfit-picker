"""Cloudinary setup — our image storage.

Importing this module configures the Cloudinary SDK once, from our settings.
Any code that needs Cloudinary imports from here, so the credentials are read
in exactly one place (same pattern as the database engine and Redis client).

`secure=True` makes Cloudinary hand back https:// URLs.
"""

import time

import cloudinary
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


def sign_upload(user_id: str) -> dict:
    """Create a short-lived 'authorization slip' for a direct browser upload.

    The signature is a fingerprint of (the upload parameters + our API secret).
    Only someone holding the secret can produce it, and the secret never leaves
    the server. The browser sends these fields to Cloudinary along with the file;
    Cloudinary recomputes the signature and accepts the upload only if it matches.
    """
    timestamp = int(time.time())
    folder = garment_folder(user_id)

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

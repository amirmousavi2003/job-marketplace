"""Safe handling of the optional profile photo: validate, re-encode, random file name.

Re-encoding through Pillow strips metadata (EXIF/GPS) and any payload hidden in the file;
the original bytes are never stored.
"""

import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_SIDE = 800
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def process_profile_image(uploaded) -> ContentFile:
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"photo": ["Image must be 2 MB or smaller."]})
    try:
        image = Image.open(uploaded)
        if image.format not in ALLOWED_FORMATS:
            raise ValidationError({"photo": ["Only JPEG, PNG or WebP images are allowed."]})
        if image.width * image.height > MAX_PIXELS:
            raise ValidationError({"photo": ["Image dimensions are too large."]})
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError({"photo": ["Upload a valid image file."]}) from exc

    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")

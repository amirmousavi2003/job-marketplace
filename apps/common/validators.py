from django.core.validators import URLValidator

_web_url = URLValidator(schemes=["http", "https"])


def http_url_validator(value):
    """User-supplied links must be http(s). A plain function on purpose: DRF silently drops
    URLValidator *instances* from model fields, which would let ftp:// links through the API."""
    _web_url(value)

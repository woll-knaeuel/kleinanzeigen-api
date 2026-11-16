"""Validation helpers for Kleinanzeigen URLs and browser request guards."""

from urllib.parse import urlsplit

ALLOWED_HOST = "kleinanzeigen.de"


def is_kleinanzeigen_url(url: str) -> bool:
    """Return whether URL is HTTPS on kleinanzeigen.de or one of its subdomains."""
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return False

    if parsed.scheme.lower() != "https" or not host:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if port not in (None, 443):
        return False
    return host == ALLOWED_HOST or host.endswith(f".{ALLOWED_HOST}")


def validate_kleinanzeigen_url(url: str) -> str:
    """Return a validated URL or raise ValueError before any browser navigation."""
    if not is_kleinanzeigen_url(url):
        raise ValueError("URL must use HTTPS and belong to kleinanzeigen.de")
    return url


async def restrict_kleinanzeigen_route(route) -> None:
    """Block browser requests outside the Kleinanzeigen HTTPS domain."""
    if not is_kleinanzeigen_url(route.request.url):
        await route.abort("blockedbyclient")
        return
    # Let context-level resource blocking handle images/scripts after this guard.
    await route.fallback()

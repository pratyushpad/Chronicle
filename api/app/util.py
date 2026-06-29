"""Small shared utilities."""
from urllib.parse import urlparse

# Two-part public suffixes where the registrable domain is the last 3 labels.
_TWO_PART_TLDS = {
    "co.uk", "com.au", "co.jp", "co.in", "com.br", "co.nz", "com.sg", "co.za",
}


def root_domain(url: str | None) -> str | None:
    """Reduce a careers URL to its registrable root domain.

    careers.robinhood.com -> robinhood.com
    https://www.lyft.com/careers -> lyft.com
    """
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc or urlparse(f"//{url}").netloc
        host = netloc.split("@")[-1].split(":")[0].lower()
        if host.startswith("www."):
            host = host[4:]
        labels = host.split(".")
        if len(labels) <= 2:
            return host or None
        last_two = ".".join(labels[-2:])
        if last_two in _TWO_PART_TLDS:
            return ".".join(labels[-3:])
        return ".".join(labels[-2:])
    except Exception:
        return None

from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_allowed_redirect_uri(uri: str) -> bool:
    """OAuth 2.1 redirect rule: `https` only, except plain `http` on a loopback host (RFC 8252 §7.3).

    Anything else (`javascript:`, `data:`, custom schemes, `http` to a remote host) is refused, because the
    consent page navigates the browser to this URI from the Mealie origin.
    """
    try:
        parts = urlsplit(uri)
        hostname = parts.hostname
    except ValueError:
        return False

    scheme = parts.scheme.lower()
    if scheme == "https":
        return bool(hostname)
    if scheme == "http":
        return hostname in LOOPBACK_HOSTS
    return False


def redirect_host(uri: str) -> str:
    """What the consent page shows as the destination: host[:port], never userinfo; the raw URI if there is no host."""
    try:
        parts = urlsplit(uri)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        return uri

    if not hostname:
        return uri
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{host}:{port}" if port else host

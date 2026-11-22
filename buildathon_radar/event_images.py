"""Fetch and cache small public raster thumbnails from selected source CDNs."""
import http.client
import ipaddress
import socket
import time
from functools import lru_cache
from urllib.parse import urlsplit

HOSTS = frozenset({"assets.devfolio.co", "mlhusercontent.com", "ethglobal.b-cdn.net",
                   "d112y698adiu2z.cloudfront.net", "d8it4huxumps7.cloudfront.net"})
MAX_BYTES = 1_000_000
TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


def image_target(url):
    try:
        parts = urlsplit(url or "")
        if (parts.scheme == "https" and parts.netloc in HOSTS and parts.path.startswith("/")
                and not parts.query and not parts.fragment):
            return parts
    except ValueError:
        pass
    return None


def _fetch(url):
    target = image_target(url)
    if not target:
        return None
    addresses = socket.getaddrinfo(target.hostname, 443, type=socket.SOCK_STREAM)
    public = [row[4][0] for row in addresses if ipaddress.ip_address(row[4][0]).is_global]
    if not public or len(public) != len(addresses):
        return None
    connection = http.client.HTTPSConnection(target.hostname, timeout=4)
    # Pin the validated address while retaining normal hostname and TLS certificate validation.
    connection._create_connection = lambda _address, timeout, source: socket.create_connection(
        (public[0], 443), timeout, source)
    try:
        connection.request("GET", target.path, headers={"Accept": ", ".join(TYPES)})
        response = connection.getresponse()
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].lower()
        size = response.getheader("Content-Length")
        if response.status != 200 or content_type not in TYPES or (size and (not size.isdecimal() or int(size) > MAX_BYTES)):
            return None
        deadline = time.monotonic() + 4
        content = bytearray()
        while len(content) <= MAX_BYTES and time.monotonic() < deadline:
            part = response.read1(min(65536, MAX_BYTES + 1 - len(content)))
            if not part:
                break
            content.extend(part)
        else:
            return None
        data = bytes(content)
        if not data.startswith(TYPES[content_type]):
            return None
        if content_type == "image/webp" and data[8:12] != b"WEBP":
            return None
        return content_type, data
    finally:
        connection.close()


@lru_cache(maxsize=32)
def _cached_thumbnail(url, time_bucket):
    try:
        return _fetch(url)
    except (OSError, ValueError, http.client.HTTPException):
        return None


def thumbnail(url):
    return _cached_thumbnail(url, int(time.time() // 3600)) if image_target(url) else None

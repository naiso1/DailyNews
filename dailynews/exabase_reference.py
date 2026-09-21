"""One public source image for exaBase; no credentials or private-network fetches."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import io
import ipaddress
from pathlib import Path
import socket
import urllib.parse
import urllib.request
import warnings

MAX_BYTES = 10 * 1024 * 1024
MODE = "source-image-v1"
MIME_TYPES = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


class ReferenceImageError(ValueError):
    pass


def public_url(value: str, *, resolve=True):
    value = html.unescape(str(value or "")).strip()
    try:
        url = urllib.parse.urlsplit(value)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                or url.port not in {None, 80, 443} or any(ord(c) < 32 for c in value)):
            raise ValueError()
        host = url.hostname.rstrip(".")
        if "." not in host and ":" not in host:
            raise ValueError()
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, url.port or 443)] if resolve else []
        if any(not address.is_global for address in addresses):
            raise ValueError()
    except (ValueError, OSError) as error:
        raise ReferenceImageError("REFERENCE_URL_REJECTED") from error
    return urllib.parse.urlunsplit((url.scheme, url.netloc, url.path, url.query, ""))


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, public_url(newurl))


@dataclass(frozen=True)
class ReferenceImage:
    source_id: str
    article_url: str
    image_url: str
    file: Path
    sha256: str
    mime: str
    width: int
    height: int

    def metadata(self):
        return {"mode": MODE, "sourceNewsId": self.source_id, "articleUrl": self.article_url,
                "imageUrl": self.image_url, "sha256": self.sha256, "mime": self.mime,
                "width": self.width, "height": self.height}


def image_info(data: bytes):
    from PIL import Image
    if not 1000 <= len(data) <= MAX_BYTES:
        raise ReferenceImageError("REFERENCE_INVALID_IMAGE")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (image.format not in MIME_TYPES or min(image.size) < 256
                        or image.width * image.height > 40_000_000 or getattr(image, "n_frames", 1) != 1):
                    raise ValueError()
                mime, extension = MIME_TYPES[image.format]
                size = image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except Exception as error:
        raise ReferenceImageError("REFERENCE_INVALID_IMAGE") from error
    return mime, extension, size


def download_reference(source_id: str, article: dict, directory: Path, *, opener=None):
    """Use configured corporate proxy while validating every redirect destination."""
    article_url = public_url(article.get("url", ""), resolve=False)
    image_url = public_url(article.get("img", ""))
    try:
        request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/png,image/jpeg,image/webp"})
        with (opener or urllib.request.build_opener(PublicRedirects())).open(request, timeout=20) as response:
            public_url(response.geturl())
            content_type = response.headers.get_content_type()
            if content_type not in {"image/jpeg", "image/png", "image/webp", "application/octet-stream"}:
                raise ReferenceImageError("REFERENCE_INVALID_IMAGE")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise ReferenceImageError("REFERENCE_INVALID_IMAGE")
            data = response.read(MAX_BYTES + 1)
    except ReferenceImageError:
        raise
    except Exception as error:
        raise ReferenceImageError("REFERENCE_DOWNLOAD_FAILED") from error
    mime, extension, size = image_info(data)
    digest = hashlib.sha256(data).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / (digest + extension)
    if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
        temporary = file.with_suffix(extension + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(file)
    return ReferenceImage(source_id, article_url, image_url, file, digest, mime, *size)


def verified_bytes(reference: ReferenceImage):
    data = reference.file.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference.sha256:
        raise ReferenceImageError("REFERENCE_CHANGED")
    mime, extension, size = image_info(data)
    if mime != reference.mime or size != (reference.width, reference.height):
        raise ReferenceImageError("REFERENCE_CHANGED")
    return data, extension

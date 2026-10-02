"""Safe image uploads (OWASP A02, A05, A06, A10).

Pipeline, in this order. Any failure rejects the file (fail closed):
 1. size limit            4. ClamAV scan (clamd INSTREAM)
 2. real type by magic    5. re-encode with Pillow (drops EXIF/GPS and hidden payloads)
 3. decode + pixel limit  6. store under a random name, never the user's filename
"""
import io
import os
import socket
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.seclog import log

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000          # blocks decompression bombs
MAX_SIDE = 1200
THUMB_SIDE = 320                 # grid cards show this small copy, not the full photo
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

_MAGIC = {b"\xff\xd8\xff": "jpeg", b"\x89PNG\r\n\x1a\n": "png"}


class UploadRejected(ValueError):
    """The file was refused. The message is safe to show to the user."""


class ScannerUnavailable(Exception):
    """ClamAV could not be reached. Uploads are refused until it is back."""


@dataclass
class ScanResult:
    clean: bool
    signature: str | None = None


def detect_type(data: bytes) -> str | None:
    """Decide the file type from its bytes. The filename and extension are ignored."""
    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class ClamAVScanner:
    """Minimal clamd client using the INSTREAM command (no extra dependency)."""

    CHUNK = 64 * 1024

    def __init__(self, host: str = "127.0.0.1", port: int = 3310,
                 socket_path: str | None = None, timeout: float = 10.0):
        self.host, self.port, self.socket_path, self.timeout = host, port, socket_path, timeout

    def _connect(self) -> socket.socket:
        try:
            if self.socket_path:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                s.connect(self.socket_path)
                return s
            return socket.create_connection((self.host, self.port), self.timeout)
        except OSError as err:
            raise ScannerUnavailable(f"ClamAV not reachable: {err}") from err

    def scan(self, data: bytes) -> ScanResult:
        try:
            with self._connect() as s:
                s.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), self.CHUNK):
                    chunk = data[i:i + self.CHUNK]
                    s.sendall(struct.pack("!I", len(chunk)) + chunk)
                s.sendall(struct.pack("!I", 0))
                reply = b""
                while not reply.endswith(b"\0") and len(reply) < 4096:
                    part = s.recv(1024)
                    if not part:
                        break
                    reply += part
        except (OSError, socket.timeout) as err:
            raise ScannerUnavailable(f"ClamAV scan failed: {err}") from err
        text = reply.rstrip(b"\0\n").decode(errors="replace")
        if text.endswith("OK"):
            return ScanResult(True)
        if text.endswith("FOUND"):
            return ScanResult(False, text.split(":", 1)[-1].replace("FOUND", "").strip())
        raise ScannerUnavailable(f"Unexpected ClamAV reply: {text!r}")   # includes "...ERROR"


def get_scanner() -> ClamAVScanner:
    """Scanner from environment: FARM_CLAMAV_HOST/PORT or FARM_CLAMAV_SOCKET."""
    return ClamAVScanner(host=os.getenv("FARM_CLAMAV_HOST", "127.0.0.1"),
                         port=int(os.getenv("FARM_CLAMAV_PORT", "3310")),
                         socket_path=os.getenv("FARM_CLAMAV_SOCKET") or None)


def save_product_image(data: bytes, dest_dir: Path, scanner=None) -> str:
    """Validate, scan, clean and store an image. Returns the stored file name."""
    scanner = scanner or get_scanner()
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("The photo is larger than 5 MB. Choose a smaller one.")
    kind = detect_type(data)
    if kind is None:
        log.warning("upload rejected: unsupported type")
        raise UploadRejected("Use a JPG, PNG or WebP photo.")
    try:                                              # decode fully: catches truncated/forged files
        with Image.open(io.BytesIO(data)) as probe:
            probe.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        log.warning("upload rejected: not a valid image")
        raise UploadRejected("That file is not a valid photo.")
    try:
        result = scanner.scan(data)
    except ScannerUnavailable as err:
        log.error("upload refused, scanner unavailable: %s", err)
        raise UploadRejected("Photo uploads are paused for a moment. Try again shortly.")
    if not result.clean:
        log.warning("upload rejected: malware signature %s", result.signature)
        raise UploadRejected("This file was blocked by the virus scan.")
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)           # apply rotation, then drop all metadata
        if img.mode != "RGB":
            background = Image.new("RGB", img.size, "white")
            background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
            img = background
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.jpg"
        img.save(dest_dir / name, "JPEG", quality=85, optimize=True)   # fresh file, no metadata
        thumb = img.copy()
        thumb.thumbnail((THUMB_SIDE, THUMB_SIDE))
        (dest_dir / "thumbs").mkdir(exist_ok=True)
        thumb.save(dest_dir / "thumbs" / name, "JPEG", quality=75, optimize=True)
    return name

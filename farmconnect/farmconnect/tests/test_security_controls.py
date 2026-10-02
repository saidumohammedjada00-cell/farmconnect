import io
import logging

import pytest
from PIL import Image

from app.security import LoginLocked, LoginThrottle
from app.uploads import (ClamAVScanner, ScannerUnavailable, UploadRejected, detect_type,
                         save_product_image)
from tests.fake_clamd import EICAR, FakeClamd


def make_image(fmt="JPEG", size=(80, 60), exif=False):
    buf = io.BytesIO()
    img = Image.new("RGB", size, (200, 30, 30))
    kwargs = {}
    if exif:
        e = Image.Exif(); e[0x010F] = "SecretCameraMaker"; kwargs["exif"] = e
    img.save(buf, fmt, **kwargs)
    return buf.getvalue()


@pytest.fixture
def clamd():
    server = FakeClamd()
    yield ClamAVScanner(port=server.port, timeout=2), server
    server.close()


# ---------- ClamAV client ----------
def test_clean_file_passes_scan(clamd):
    scanner, server = clamd
    assert scanner.scan(b"hello").clean
    assert server.received == b"hello"


def test_eicar_is_detected(clamd):
    scanner, _ = clamd
    result = scanner.scan(EICAR)
    assert not result.clean and result.signature == "Eicar-Test-Signature"


def test_large_file_is_streamed_in_chunks(clamd):
    scanner, server = clamd
    payload = b"a" * (200 * 1024)
    assert scanner.scan(payload).clean and server.received == payload


def test_unreachable_scanner_raises():
    with pytest.raises(ScannerUnavailable):
        ClamAVScanner(port=1, timeout=0.5).scan(b"x")


def test_scanner_error_reply_is_not_treated_as_clean():
    server = FakeClamd(reply=b"stream: INSTREAM size limit exceeded. ERROR\0")
    try:
        with pytest.raises(ScannerUnavailable):
            ClamAVScanner(port=server.port, timeout=2).scan(b"x")
    finally:
        server.close()


# ---------- upload pipeline ----------
def test_valid_photo_is_stored_under_random_name(clamd, tmp_path):
    name = save_product_image(make_image(), tmp_path, clamd[0])
    assert name.endswith(".jpg") and len(name) == 36 and (tmp_path / name).exists()


def test_exif_metadata_is_stripped(clamd, tmp_path):
    data = make_image(exif=True)
    assert b"SecretCameraMaker" in data
    name = save_product_image(data, tmp_path, clamd[0])
    assert b"SecretCameraMaker" not in (tmp_path / name).read_bytes()


def test_png_and_big_images_are_converted_and_shrunk(clamd, tmp_path):
    name = save_product_image(make_image("PNG", (3000, 2000)), tmp_path, clamd[0])
    with Image.open(tmp_path / name) as out:
        assert out.format == "JPEG" and max(out.size) <= 1200


def test_fake_extension_does_not_matter(clamd, tmp_path):
    assert detect_type(b"MZ\x90\x00 not an image") is None
    with pytest.raises(UploadRejected, match="JPG, PNG or WebP"):
        save_product_image(b"MZ\x90\x00 pretend.jpg", tmp_path, clamd[0])


def test_truncated_image_rejected(clamd, tmp_path):
    with pytest.raises(UploadRejected, match="not a valid"):
        save_product_image(make_image()[:60], tmp_path, clamd[0])


def test_oversize_and_empty_rejected(clamd, tmp_path):
    with pytest.raises(UploadRejected, match="5 MB"):
        save_product_image(b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024), tmp_path, clamd[0])
    with pytest.raises(UploadRejected, match="empty"):
        save_product_image(b"", tmp_path, clamd[0])


def test_infected_file_blocked_and_nothing_saved(clamd, tmp_path, caplog):
    infected = make_image() + EICAR            # valid JPEG with a signature appended
    with caplog.at_level(logging.WARNING, logger="farmconnect.security"):
        with pytest.raises(UploadRejected, match="virus scan"):
            save_product_image(infected, tmp_path, clamd[0])
    assert list(tmp_path.iterdir()) == []
    assert "Eicar-Test-Signature" in caplog.text


def test_scanner_down_fails_closed(tmp_path):
    with pytest.raises(UploadRejected, match="paused"):
        save_product_image(make_image(), tmp_path, ClamAVScanner(port=1, timeout=0.5))
    assert list(tmp_path.iterdir()) == []


# ---------- login throttle ----------
def test_throttle_locks_after_five_failures_and_expires():
    now = [0.0]
    t = LoginThrottle(max_attempts=5, window=900, lockout=900, clock=lambda: now[0])
    for _ in range(4):
        assert t.failure("a@b.com") is False
    assert t.failure("a@b.com") is True
    with pytest.raises(LoginLocked):
        t.check("a@b.com")
    t.check("other@b.com")                        # other accounts unaffected
    now[0] = 901
    t.check("a@b.com")                            # lock has expired


def test_old_failures_age_out_of_window():
    now = [0.0]
    t = LoginThrottle(max_attempts=3, window=100, clock=lambda: now[0])
    t.failure("k"); t.failure("k")
    now[0] = 500
    assert t.failure("k") is False


def test_repository_locks_even_correct_password_and_logs(users, caplog):
    users.create("Ada", "ada@mail.com", "password1")
    with caplog.at_level(logging.INFO, logger="farmconnect.security"):
        for _ in range(5):
            assert users.authenticate("ada@mail.com", "wrong-pass") is None
        with pytest.raises(LoginLocked):
            users.authenticate("ada@mail.com", "password1")
    assert "account locked" in caplog.text
    assert "ada@mail.com" not in caplog.text and "wrong-pass" not in caplog.text


def test_success_resets_failure_count(users):
    users.create("Ada", "ada@mail.com", "password1")
    for _ in range(4):
        users.authenticate("ada@mail.com", "wrong-pass")
    assert users.authenticate("ada@mail.com", "password1")
    for _ in range(4):
        assert users.authenticate("ada@mail.com", "wrong-pass") is None   # still not locked

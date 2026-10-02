"""Password hashing and input validation (OWASP: cryptographic failure, injection)."""
import hashlib
import hmac
import os
import re

from app.config import MIN_PASSWORD_LENGTH

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=_N, r=_R, p=_P)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def validate_email(email: str) -> bool:
    return bool(_EMAIL.match(email or ""))


def validate_password(password: str) -> bool:
    return bool(password) and len(password) >= MIN_PASSWORD_LENGTH


# ---------- login throttling (OWASP A07 Authentication Failures) ----------
import time
from collections import defaultdict, deque


class LoginLocked(Exception):
    """Too many failed attempts; ask the user to wait."""


class LoginThrottle:
    """Lock an account for `lockout` seconds after `max_attempts` failures inside `window`."""

    def __init__(self, max_attempts: int = 5, window: float = 900, lockout: float = 900,
                 clock=time.monotonic):
        self.max_attempts, self.window, self.lockout, self.clock = max_attempts, window, lockout, clock
        self._fails: dict[str, deque] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}

    def check(self, key: str) -> None:
        until = self._locked_until.get(key)
        if until is not None:
            if self.clock() < until:
                raise LoginLocked("Too many attempts. Try again in 15 minutes.")
            del self._locked_until[key]
            self._fails.pop(key, None)

    def failure(self, key: str) -> bool:
        """Record a failure. Returns True if this failure locked the account."""
        now, q = self.clock(), self._fails[key]
        q.append(now)
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_attempts:
            self._locked_until[key] = now + self.lockout
            return True
        return False

    def success(self, key: str) -> None:
        self._fails.pop(key, None)
        self._locked_until.pop(key, None)


class RateLimiter:
    """Allow `max_calls` per `per_seconds` for each key (for example, one user's searches).

    Protects the external stores and your hosting bill. Share ONE instance between sessions.
    """

    def __init__(self, max_calls: int = 10, per_seconds: float = 60, clock=time.monotonic):
        self.max_calls, self.per_seconds, self.clock = max_calls, per_seconds, clock
        self._calls: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        q = self._calls.setdefault(key, deque())
        while q and now - q[0] >= self.per_seconds:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        if len(self._calls) > 10_000:                      # forget idle keys: bounded memory
            for k in [k for k, v in self._calls.items() if not v or now - v[-1] >= self.per_seconds]:
                del self._calls[k]
        return True

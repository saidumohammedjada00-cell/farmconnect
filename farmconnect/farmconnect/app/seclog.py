"""Security event log (OWASP A09). Never log passwords, tokens or full emails."""
import hashlib
import logging

log = logging.getLogger("farmconnect.security")


def who(email: str) -> str:
    """Short, non-reversible tag so events can be correlated without storing the email."""
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:10]

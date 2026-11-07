"""Password hashing, password policy, session-token helpers and a small rate limiter."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()          # Argon2id with the library's current recommended parameters
# Verified when the e-mail is unknown so that "no such user" and "wrong password" take similar time.
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-only-for-timing")

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
_COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd123", "1234567890", "12345678910",
    "123456789012", "qwertyuiop", "qwerty12345", "qwerty123456", "iloveyou123", "letmein1234", "welcome1234",
    "admin12345", "administrator", "changeme123", "abcdefghij", "abc1234567", "0123456789", "1q2w3e4r5t",
    "student123", "student1234", "p@ssw0rd123", "password!23",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work check. Pass ``None`` for an unknown user to spend the same time."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    """Reasons a password is not acceptable (empty list = fine)."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"must be at most {MAX_PASSWORD_LENGTH} characters long")
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(password)) < 4:
        problems.append("is too common or too repetitive")
    squashed = "".join(ch for ch in lowered if ch.isalnum())
    words = [w for w in (name or "").lower().replace(".", " ").split() if len(w) >= 4]
    for secret in [(email or "").split("@")[0], (name or ""), *words]:
        key = "".join(ch for ch in secret.lower() if ch.isalnum())
        if len(key) >= 4 and key in squashed:
            problems.append("must not contain your name or e-mail address")
            break
    if password.strip() != password:
        problems.append("must not start or end with a space")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)        # 256 bits


def hash_token(token: str) -> str:
    """Session tokens are high-entropy random strings, so a plain SHA-256 is the right storage format."""
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """Sliding-window limiter kept in process memory.

    Suitable for the single-process deployment this project targets (one uvicorn worker). With several
    workers or hosts the counters would not be shared -- use a shared store (e.g. Redis) or a reverse
    proxy for that. Account lockout (stored in the database) still applies across workers.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> float:
        """Record an event; return 0 if allowed, else the seconds to wait."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, window_seconds - (now - q[0]))
            q.append(now)
            return 0.0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

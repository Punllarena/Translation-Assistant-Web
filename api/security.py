import base64
import hashlib
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken

from api.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt_secret(blob: bytes) -> str:
    try:
        return _fernet().decrypt(blob).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("secret could not be decrypted") from exc


class LoginLimiter:
    """Per-key fixed-window failure counter.

    # ponytail: in-memory, single process. Move to a table when the
    # deployment runs more than one API replica.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        return q

    def check(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) < self.max_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


_settings = get_settings()
login_limiter = LoginLimiter(_settings.login_max_attempts, _settings.login_window_seconds)

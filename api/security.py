import base64
import hashlib
import heapq
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken

from api.config import get_settings

_hasher = PasswordHasher()

# Upper bound on keys tracked by a LoginLimiter; the stalest keys are evicted first.
MAX_TRACKED_KEYS = 10_000


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
    # surrogatepass: a malformed cookie with lone surrogates must hash (and miss), not raise.
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


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
    """Per-key sliding-window failure counter, thread-safe.

    Failures older than window_seconds stop counting. Keys with no live failures
    are removed, and the map is capped at MAX_TRACKED_KEYS (stalest evicted first).

    # ponytail: in-memory and single-process. The MAX_TRACKED_KEYS cap bounds memory
    # against source-address rotation, but a limit enforced per process does not
    # hold across replicas. Replace with a shared table when the deployment runs
    # more than one API replica.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str, now: float) -> deque[float] | None:
        """Return the key's unexpired failures, dropping the key if none remain. Lock held by caller."""
        q = self._failures.get(key)
        if q is None:
            return None
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        if not q:
            del self._failures[key]
            return None
        return q

    def check(self, key: str) -> bool:
        with self._lock:
            q = self._live(key, time.monotonic())
            return q is None or len(q) < self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            q = self._live(key, now)
            if q is None:
                q = deque()
                self._failures[key] = q
            q.append(now)
            excess = len(self._failures) - MAX_TRACKED_KEYS
            if excess > 0:
                stalest = heapq.nsmallest(
                    excess, self._failures, key=lambda k: self._failures[k][-1]
                )
                for k in stalest:
                    del self._failures[k]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


_settings = get_settings()
login_limiter = LoginLimiter(_settings.login_max_attempts, _settings.login_window_seconds)

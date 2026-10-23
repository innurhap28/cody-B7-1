"""Versioned scrypt credentials, with read compatibility for existing bcrypt rows."""
import base64
import hashlib
import hmac
import secrets

import bcrypt

MAX_PASSWORD_BYTES = 72
SCRYPT_N, SCRYPT_R, SCRYPT_P = 16384, 8, 1


def _derive(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                          p=SCRYPT_P, dklen=32, maxmem=64 * 1024 * 1024)


def _pack(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(password) < 8 or len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError("Password length outside registration limits")
    salt = secrets.token_bytes(16)
    return "$".join(("scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     _pack(salt), _pack(_derive(raw, salt))))


def is_legacy_hash(encoded: str) -> bool:
    return encoded.startswith(("$2a$", "$2b$", "$2y$"))


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(encoded, str):
        return False
    try:
        raw = password.encode("utf-8")
        if not raw or len(raw) > MAX_PASSWORD_BYTES:
            return False
        if is_legacy_hash(encoded):
            return bcrypt.checkpw(raw, encoded.encode("ascii"))
        algorithm, n, r, p, salt64, digest64 = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)):
            return False
        salt = base64.b64decode(salt64, altchars=b"-_", validate=True)
        digest = base64.b64decode(digest64, altchars=b"-_", validate=True)
        if len(salt) != 16 or len(digest) != 32:
            return False
        return hmac.compare_digest(_derive(raw, salt), digest)
    except (ValueError, TypeError, UnicodeError):
        return False

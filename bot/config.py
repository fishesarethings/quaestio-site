"""Shared config + crypto helpers for Quaestio (bot + web dashboard).

Sensitive values are encrypted at rest with Fernet (AES128-CBC + HMAC) using a
key stored in a 0600 file. Encrypted values are stored as `enc:<token>`. The
bot transparently decrypts on read; the dashboard encrypts on write.
"""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _default_keyfile() -> str:
    p = os.environ.get("QUAESTIO_KEY_FILE", "")
    if p:
        return p
    if sys.platform == "win32":
        return os.path.join(os.environ.get("USERPROFILE", ""), ".quaestio", "keyfile")
    if sys.platform == "darwin":
        return os.path.join(str(Path.home()), ".quaestio", "keyfile")
    return "/etc/quaestio/keyfile"


KEY_FILE = _default_keyfile()
SENSITIVE_KEYS = {
    "ai_instructions",
    "ai_endpoint",
    "welcome_message",
    "tag_editor",
}

_f = None


def _fernet():
    global _f
    if _f is not None:
        return _f
    p = Path(KEY_FILE)
    if not p.exists():
        raise RuntimeError(f"Quaestio keyfile missing at {KEY_FILE} (run install to create it)")
    _f = Fernet(p.read_bytes().strip())
    return _f


def create_keyfile(path=None):
    """Create a fresh key file (0600). Call once at install time."""
    p = Path(path or KEY_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(Fernet.generate_key())
        p.chmod(0o600)
    return p


def encrypt(value: str) -> str:
    if value == "":
        return ""
    return "enc:" + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value or not value.startswith("enc:"):
        return value
    try:
        return _fernet().decrypt(value[4:].encode()).decode()
    except InvalidToken:
        return ""


def maybe_encrypt(key: str, value: str) -> str:
    return encrypt(value) if key in SENSITIVE_KEYS else value


def maybe_decrypt(key: str, value: str) -> str:
    return decrypt(value) if key in SENSITIVE_KEYS else value

"""Encryption utilities for protecting PII (personally identifiable information).

User data is encrypted at rest using AES-256-GCM via Fernet-compatible scheme.
The encryption key is derived from the ENCRYPTION_KEY environment variable.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet

from app.core.config import settings

# Derive a Fernet-compatible key from the configured encryption key
_raw_key = settings.ENCRYPTION_KEY.encode("utf-8")
_derived_key = hashlib.sha256(_raw_key).digest()
_fernet_key = base64.urlsafe_b64encode(_derived_key)
_fernet = Fernet(_fernet_key)


def encrypt_pii(plaintext: str) -> str:
    """Encrypt a PII string for storage in DB.

    Returns base64-encoded ciphertext.
    """
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_pii(ciphertext: str) -> str:
    """Decrypt a PII string from DB.

    Returns the original plaintext.
    """
    if not ciphertext:
        return ""
    return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def hash_identifier(value: str) -> str:
    """Create a one-way hash of an identifier (for lookups without decryption).

    Used for indexed fields like email where we need to search
    but don't want to store plaintext.
    """
    if not value:
        return ""
    salted = f"{settings.ENCRYPTION_KEY}:{value}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()

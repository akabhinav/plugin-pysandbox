"""Credential encryption and storage using Fernet (AES-128-CBC + HMAC-SHA256)."""

from __future__ import annotations

import json

from cryptography.fernet import Fernet

import structlog

logger = structlog.get_logger()


class SecretManager:
    """Encrypts plugin credentials. Decrypts only when needed."""

    def __init__(self, encryption_key: str | bytes) -> None:
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        self._fernet = Fernet(encryption_key)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key."""
        return Fernet.generate_key().decode()

    def encrypt(self, credentials: dict[str, str]) -> str:
        """Encrypt a credentials dict. Returns base64-encoded ciphertext."""
        plaintext = json.dumps(credentials).encode()
        return self._fernet.encrypt(plaintext).decode()

    def decrypt(self, encrypted: str) -> dict[str, str]:
        """Decrypt a previously encrypted credentials string."""
        plaintext = self._fernet.decrypt(encrypted.encode())
        return json.loads(plaintext)

    def rotate(self, encrypted: str, new_key: str | bytes) -> str:
        """Re-encrypt with a new key."""
        raw = self.decrypt(encrypted)
        new_fernet = Fernet(new_key if isinstance(new_key, bytes) else new_key.encode())
        return new_fernet.encrypt(json.dumps(raw).encode()).decode()

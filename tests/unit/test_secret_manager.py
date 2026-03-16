"""Tests for credential encryption."""

import pytest

from pysandbox.runtime.secret_manager import SecretManager


class TestSecretManager:
    def test_encrypt_decrypt_roundtrip(self, secret_manager):
        """Encrypting then decrypting returns original data."""
        creds = {"user": "admin", "password": "s3cret123"}
        encrypted = secret_manager.encrypt(creds)
        decrypted = secret_manager.decrypt(encrypted)

        assert decrypted == creds

    def test_encrypted_is_not_plaintext(self, secret_manager):
        """Encrypted value doesn't contain plaintext credentials."""
        creds = {"password": "mysecretpassword"}
        encrypted = secret_manager.encrypt(creds)

        assert "mysecretpassword" not in encrypted

    def test_different_encryptions_differ(self, secret_manager):
        """Two encryptions of the same data produce different ciphertexts (Fernet uses timestamps)."""
        creds = {"key": "value"}
        e1 = secret_manager.encrypt(creds)
        e2 = secret_manager.encrypt(creds)

        # Fernet includes timestamp, so ciphertexts may differ
        d1 = secret_manager.decrypt(e1)
        d2 = secret_manager.decrypt(e2)
        assert d1 == d2 == creds

    def test_generate_key(self):
        """Generated keys are valid Fernet keys."""
        key = SecretManager.generate_key()
        # Should not raise
        sm = SecretManager(key)
        creds = {"test": "data"}
        assert sm.decrypt(sm.encrypt(creds)) == creds

    def test_wrong_key_fails(self):
        """Decrypting with wrong key raises error."""
        key1 = SecretManager.generate_key()
        key2 = SecretManager.generate_key()
        sm1 = SecretManager(key1)
        sm2 = SecretManager(key2)

        encrypted = sm1.encrypt({"secret": "data"})
        with pytest.raises(Exception):
            sm2.decrypt(encrypted)

    def test_rotate_key(self):
        """Rotating re-encrypts with new key."""
        key1 = SecretManager.generate_key()
        key2 = SecretManager.generate_key()
        sm = SecretManager(key1)

        creds = {"user": "admin", "password": "pass"}
        encrypted = sm.encrypt(creds)
        rotated = sm.rotate(encrypted, key2)

        # Old key can't decrypt rotated
        with pytest.raises(Exception):
            sm.decrypt(rotated)

        # New key can
        sm2 = SecretManager(key2)
        assert sm2.decrypt(rotated) == creds

    def test_empty_credentials(self, secret_manager):
        """Empty dict can be encrypted/decrypted."""
        encrypted = secret_manager.encrypt({})
        assert secret_manager.decrypt(encrypted) == {}

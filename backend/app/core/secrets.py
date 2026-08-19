from __future__ import annotations

import base64
import hashlib
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.config import settings


class SecretManager:
    """Envelope-like local Secret adapter; the master key stays outside MySQL."""

    def __init__(self, master_key: str | None = None) -> None:
        raw = (master_key or settings.app_secret_key).encode("utf-8")
        self._key = hashlib.sha256(raw).digest()

    def encrypt(self, value: dict[str, str]) -> tuple[str, str]:
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, None)
        encoded_nonce = base64.urlsafe_b64encode(nonce).decode("ascii")
        encoded_ciphertext = base64.urlsafe_b64encode(ciphertext).decode("ascii")
        return encoded_nonce, encoded_ciphertext

    def decrypt(self, nonce_b64: str, ciphertext_b64: str) -> dict[str, str]:
        nonce = base64.urlsafe_b64decode(nonce_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
        data = AESGCM(self._key).decrypt(nonce, ciphertext, None)
        return json.loads(data.decode("utf-8"))


__all__ = ["SecretManager"]

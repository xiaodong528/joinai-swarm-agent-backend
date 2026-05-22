from __future__ import annotations

import base64
import hashlib
import hmac
import os


class SecretBox:
    def __init__(self, key: str | None = None) -> None:
        raw_key = key or os.getenv("CHAT_SECRET_KEY")
        if not raw_key:
            raise RuntimeError("CHAT_SECRET_KEY is required for encrypted chat session secrets")
        self._key = hashlib.sha256(raw_key.encode("utf-8")).digest()
        self._fernet = self._build_fernet(raw_key)

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        data = value.encode("utf-8")
        if self._fernet is not None:
            return "fernet:" + self._fernet.encrypt(data).decode("ascii")
        nonce = os.urandom(16)
        stream = self._keystream(nonce, len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, stream))
        tag = hmac.new(self._key, nonce + ciphertext, hashlib.sha256).digest()
        return "v1:" + base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("fernet:"):
            if self._fernet is None:
                raise ValueError("cryptography is required to decrypt this secret")
            return self._fernet.decrypt(value.removeprefix("fernet:").encode("ascii")).decode("utf-8")
        if not value.startswith("v1:"):
            raise ValueError("unsupported encrypted secret format")
        payload = base64.urlsafe_b64decode(value.removeprefix("v1:").encode("ascii"))
        nonce = payload[:16]
        tag = payload[16:48]
        ciphertext = payload[48:]
        expected = hmac.new(self._key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("encrypted secret failed integrity check")
        stream = self._keystream(nonce, len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream)).decode("utf-8")

    def _keystream(self, nonce: bytes, size: int) -> bytes:
        chunks: list[bytes] = []
        counter = 0
        while sum(len(chunk) for chunk in chunks) < size:
            counter_bytes = counter.to_bytes(8, "big")
            chunks.append(hmac.new(self._key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        return b"".join(chunks)[:size]

    def _build_fernet(self, raw_key: str):
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            return None
        fernet_key = base64.urlsafe_b64encode(self._key)
        return Fernet(fernet_key)

"""Security helpers including encryption/decryption utilities."""
from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(RuntimeError):
    """Raised when encrypted payloads cannot be decrypted."""


@dataclass
class SecretsBox:
    """Wrapper around :class:`~cryptography.fernet.Fernet` for convenience."""

    key: str

    def __post_init__(self) -> None:
        try:
            self._fernet = Fernet(self.key)
        except ValueError as exc:
            raise EncryptionError("Encryption key is not a valid Fernet key") from exc

    def encrypt(self, value: str) -> str:
        token = self._fernet.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, token: str) -> str:
        try:
            data = self._fernet.decrypt(token.encode("utf-8"))
        except InvalidToken as exc:
            raise EncryptionError("Failed to decrypt token; invalid key or payload") from exc
        return data.decode("utf-8")


def mask_phone(phone: str) -> str:
    """Mask a phone number while keeping last four digits visible."""

    digits = phone[-4:]
    return f"***{digits}" if len(phone) > 4 else "***"

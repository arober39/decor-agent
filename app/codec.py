"""AES-256-GCM payload codec for encryption-at-rest.

Sits in Temporal's data converter. ``encode`` encrypts every payload before it
leaves this process for the Temporal server; ``decode`` decrypts on the way back.
Because this runs client-side, the Temporal server only ever stores *ciphertext*
— so PII in workflow inputs and activity results is encrypted in event history.

Toggle: only active when ``ENCRYPTION_KEY`` is set. The worker and the FastAPI
server load it; the time-skipping test environment does not, so tests run
unencrypted and stay green. Mirrors Temporal's official Python encryption sample.
"""

import base64
import dataclasses
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from temporalio.api.common.v1 import Payload
from temporalio.converter import (
    DataConverter, PayloadCodec, default as _default_converter,
)

from app.config import get_settings

_ENCODING = b"binary/encrypted"   # marker so decode() knows a payload is ours
_NONCE_LEN = 12                   # AES-GCM standard nonce length


def _load_key() -> bytes | None:
    raw = get_settings().encryption_key.strip()
    if not raw:
        return None
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("ENCRYPTION_KEY must decode to 32 bytes (AES-256).")
    return key


class EncryptionCodec(PayloadCodec):
    """Encrypts/decrypts every payload with AES-256-GCM."""

    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)

    async def encode(self, payloads):
        out = []
        for p in payloads:
            nonce = os.urandom(_NONCE_LEN)
            ciphertext = self._aead.encrypt(nonce, p.SerializeToString(), None)
            out.append(Payload(metadata={"encoding": _ENCODING},
                               data=nonce + ciphertext))   # nonce prepended for decode
        return out

    async def decode(self, payloads):
        out = []
        for p in payloads:
            if p.metadata.get("encoding") != _ENCODING:
                out.append(p)            # not ours (e.g. written before encryption) — pass through
                continue
            nonce, ciphertext = p.data[:_NONCE_LEN], p.data[_NONCE_LEN:]
            inner = Payload()
            inner.ParseFromString(self._aead.decrypt(nonce, ciphertext, None))
            out.append(inner)
        return out


def get_codec() -> EncryptionCodec | None:
    """Return a codec if ENCRYPTION_KEY is set, else None (encryption off)."""
    key = _load_key()
    return EncryptionCodec(key) if key else None


def data_converter() -> DataConverter:
    """Default data converter, wrapped with the encryption codec when a key is
    set. Both the worker and the FastAPI client use this so payloads round-trip."""
    codec = get_codec()
    if codec is None:
        return _default_converter()
    return dataclasses.replace(_default_converter(), payload_codec=codec)

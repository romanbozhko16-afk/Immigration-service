"""Authenticated encryption (AES-256-GCM) for case data.

Envelope scheme: every case has its own random data key; the data key is stored only in
wrapped form, encrypted with the master key from the environment. Every ciphertext is bound
to its context (case id + field) through associated data, so a ciphertext copied to another
case or field fails to decrypt instead of showing someone else's data.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class DecryptionError(Exception):
    """Wrong key, wrong context, or tampered ciphertext."""


def generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=KEY_BYTES * 8)


def encode_key(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode()


def decode_key(text: str) -> bytes:
    key = base64.urlsafe_b64decode(text.encode())
    if len(key) != KEY_BYTES:
        raise ValueError(f"key must be {KEY_BYTES} bytes")
    return key


def encrypt(key: bytes, plaintext: bytes, context: str) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, context.encode())


def decrypt(key: bytes, blob: bytes, context: str) -> bytes:
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, context.encode())
    except InvalidTag as exc:
        raise DecryptionError("cannot decrypt: wrong key, wrong context, or tampered data") from exc

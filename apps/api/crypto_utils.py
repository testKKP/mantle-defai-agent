"""
AES-GCM encryption/decryption utilities for on-chain signal encryption.
"""

import os
import json
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from web3 import Web3

SIGNAL_ENCRYPTION_KEY = os.getenv("SIGNAL_ENCRYPTION_KEY", get_random_bytes(32).hex())


def _get_key_bytes() -> bytes:
    """Normalize encryption key to 32 bytes."""
    key_hex = SIGNAL_ENCRYPTION_KEY
    if key_hex.startswith("0x"):
        key_hex = key_hex[2:]
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) < 32:
        key_bytes = key_bytes.ljust(32, b"\x00")
    elif len(key_bytes) > 32:
        key_bytes = key_bytes[:32]
    return key_bytes


def encrypt_signal(plaintext: str) -> tuple[bytes, bytes]:
    """Encrypt signal plaintext with AES-GCM, return (ciphertext, nonce)."""
    key = _get_key_bytes()
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    # Prepend authentication tag so decryption can verify integrity
    return ciphertext + tag, nonce


def decrypt_signal(ciphertext: bytes, nonce: bytes) -> str:
    """Decrypt signal ciphertext with AES-GCM."""
    key = _get_key_bytes()
    if len(ciphertext) < 16:
        raise ValueError("Invalid ciphertext: too short")
    # Split ciphertext and auth tag
    actual_ciphertext = ciphertext[:-16]
    tag = ciphertext[-16:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(actual_ciphertext, tag)
    return plaintext.decode("utf-8")


def pack_encrypted_signal(ciphertext: bytes, nonce: bytes) -> bytes:
    """Pack nonce + ciphertext + tag into a single bytes object for on-chain storage."""
    return nonce + ciphertext


def unpack_encrypted_signal(packed: bytes) -> tuple[bytes, bytes]:
    """Unpack on-chain bytes into (ciphertext, nonce). Expects nonce || ciphertext || tag."""
    if len(packed) < 28:
        raise ValueError("Invalid packed data: too short")
    nonce = packed[:12]
    ciphertext = packed[12:]
    return ciphertext, nonce


def hash_signal(plaintext: str) -> str:
    """Return keccak256 hash of plaintext for integrity verification."""
    return Web3.keccak(text=plaintext).hex()

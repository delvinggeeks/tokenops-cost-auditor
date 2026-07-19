"""Source-credential encryption (PLAN-V15 V-D1; R-CONNECT key handling).

HKDF-SHA256(SECRET_KEY, info="tokenops-source-credentials") derives a
dedicated 32-byte key, wrapped as Fernet (AES-128-CBC + HMAC, versioned,
timestamped). Decryption happens only in the pull path; revoke deletes the
ciphertext. Credentials never appear in logs, repr, or error messages —
this module deliberately imports no logging machinery (T-KEY-03 guard).
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_INFO = b"tokenops-source-credentials"


class CredentialError(Exception):
    """Raised on decryption failure. Message is user-safe by construction."""


def _fernet(secret_key: str) -> Fernet:
    material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_credential(secret_key: str, plaintext: str) -> str:
    return _fernet(secret_key).encrypt(plaintext.encode()).decode()


def decrypt_credential(secret_key: str, token: str) -> str:
    try:
        return _fernet(secret_key).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CredentialError("stored credential cannot be decrypted") from exc

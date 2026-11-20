"""Cifrado de secretos para APIs monitoreadas; la clave vive fuera de la base."""

import os
from binascii import Error as Base64Error

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()


class CredentialError(ValueError):
    pass


def _cipher() -> Fernet:
    key = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")
    if not key:
        raise CredentialError("Configura CREDENTIALS_ENCRYPTION_KEY en .env para guardar credenciales.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError, Base64Error) as exc:
        raise CredentialError("CREDENTIALS_ENCRYPTION_KEY no es una clave Fernet válida.") from exc


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted_secret: str) -> str:
    try:
        return _cipher().decrypt(encrypted_secret.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError) as exc:
        raise CredentialError("No se pudo descifrar la credencial. Revisa la clave de cifrado del servidor.") from exc

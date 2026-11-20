"""Validación y edición de autenticación de una API registrada."""

import re
from urllib.parse import urlparse

from ..infrastructure.credentials import CredentialError, encrypt_secret
from ..infrastructure.models import ApiCredential, ApiEndpoint

AUTH_TYPES = {"none", "bearer", "api_key_header", "basic"}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
FORBIDDEN_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "cookie", "proxy-authorization", "proxy-authenticate"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def configure_authentication(
    api: ApiEndpoint,
    auth_type: str,
    header_name: str,
    username: str,
    secret: str,
) -> None:
    """Un secreto vacío al editar conserva el anterior solo si el tipo no cambia."""
    auth_type = auth_type.strip()
    header_name = header_name.strip()
    username = username.strip()
    if auth_type not in AUTH_TYPES:
        raise CredentialError("Selecciona un tipo de autenticación válido.")
    if auth_type == "none":
        api.credential = None
        return
    parsed = urlparse(api.url)
    if parsed.scheme != "https" and (parsed.hostname or "").lower() not in LOCAL_HOSTS:
        raise CredentialError("Las credenciales requieren HTTPS; HTTP solo se permite en localhost.")
    if auth_type == "api_key_header":
        if not header_name or len(header_name) > 80 or not HEADER_NAME.fullmatch(header_name) or header_name.lower() in FORBIDDEN_HEADERS:
            raise CredentialError("Indica un nombre de header válido para la API key.")
    else:
        header_name = ""
    if auth_type == "basic":
        if not username or len(username) > 160 or ":" in username or any(ord(char) < 32 for char in username):
            raise CredentialError("Indica un usuario válido para autenticación Basic.")
    else:
        username = ""
    if len(secret) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in secret):
        raise CredentialError("El secreto contiene caracteres no permitidos o es demasiado largo.")
    previous = api.credential
    if not secret and (previous is None or previous.auth_type != auth_type):
        raise CredentialError("Ingresa la clave o token para este tipo de autenticación.")
    encrypted = encrypt_secret(secret) if secret else previous.encrypted_secret
    if previous is None:
        api.credential = ApiCredential(auth_type=auth_type, header_name=header_name or None, username=username or None, encrypted_secret=encrypted)
    else:
        previous.auth_type = auth_type
        previous.header_name = header_name or None
        previous.username = username or None
        previous.encrypted_secret = encrypted

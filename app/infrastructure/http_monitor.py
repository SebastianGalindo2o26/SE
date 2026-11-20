import ipaddress
import os
import socket
import time
from urllib.parse import urlparse

import httpx

from .credentials import CredentialError, decrypt_secret
from .models import ApiCredential


class UnsafeDestination(ValueError):
    pass


NAT64_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.is_global
        if any(address in network for network in NAT64_NETWORKS):
            return False
    return True


def _resolve_destination(url: str) -> tuple[str, str]:
    """Valida el destino y devuelve una IP concreta para evitar otra resolución al conectar."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeDestination("La URL del destino no es válida.") from exc
    if parsed.scheme not in ("http", "https") or not host or "@" in parsed.netloc:
        raise UnsafeDestination("Use una URL HTTP/HTTPS válida sin credenciales embebidas.")
    host = host.rstrip(".").lower()
    allowed_private = {h.strip().lower() for h in os.getenv("ALLOWED_PRIVATE_HOSTS", "localhost,127.0.0.1,::1").split(",") if h.strip()}
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = list(dict.fromkeys(ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, port)))
        except socket.gaierror as exc:
            raise UnsafeDestination("No se pudo resolver el host de destino.") from exc
    if not addresses:
        raise UnsafeDestination("El host no tiene direcciones de destino disponibles.")
    if any(not _is_public_address(address) for address in addresses) and host not in allowed_private:
        raise UnsafeDestination("El destino resuelve a una dirección privada; agréguelo a ALLOWED_PRIVATE_HOSTS si es una API autorizada.")
    selected = sorted(addresses, key=lambda address: (address.version != 4, str(address)))[0]
    return host, str(selected)


def validate_destination(url: str) -> None:
    _resolve_destination(url)


def _request_auth(credential: ApiCredential | None) -> tuple[dict[str, str], httpx.Auth | None]:
    if credential is None:
        return {}, None
    secret = decrypt_secret(credential.encrypted_secret)
    if credential.auth_type == "bearer":
        return {"Authorization": f"Bearer {secret}"}, None
    if credential.auth_type == "api_key_header" and credential.header_name:
        return {credential.header_name: secret}, None
    if credential.auth_type == "basic" and credential.username:
        return {}, httpx.BasicAuth(credential.username, secret)
    raise CredentialError("La configuración de autenticación de esta API no es válida.")


def check_api(url: str, credential: ApiCredential | None = None) -> dict:
    _, address = _resolve_destination(url)
    headers, auth = _request_auth(credential)
    original_url = httpx.URL(url)
    pinned_url = original_url.copy_with(host=address)
    headers["Host"] = original_url.netloc.decode("ascii")
    timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(pinned_url, headers=headers, auth=auth, extensions={"sni_hostname": original_url.host})
        return {"status_code": response.status_code, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": None, "error_message": None}
    except httpx.TimeoutException as exc:
        message = "La solicitud excedió el tiempo límite." if credential else str(exc) or "La solicitud excedió el tiempo límite."
        return {"status_code": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": "timeout", "error_message": message}
    except httpx.RequestError as exc:
        message = "Error de conexión con el destino." if credential else str(exc)
        return {"status_code": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": "connection", "error_message": message}

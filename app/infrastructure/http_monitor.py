import ipaddress
import os
import socket
import time
from urllib.parse import urlparse

import httpx


class UnsafeDestination(ValueError):
    pass


def validate_destination(url: str) -> None:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeDestination("La URL del destino no es válida.") from exc
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        raise UnsafeDestination("Use una URL HTTP/HTTPS válida sin credenciales embebidas.")
    host = host.rstrip(".").lower()
    allowed_targets = {h.strip().rstrip(".").lower() for h in os.getenv("ALLOWED_TARGET_HOSTS", "localhost,127.0.0.1,::1").split(",") if h.strip()}
    if host not in allowed_targets:
        raise UnsafeDestination("El host no está autorizado; agréguelo a ALLOWED_TARGET_HOSTS en .env.")
    allowed_private = {h.strip().lower() for h in os.getenv("ALLOWED_PRIVATE_HOSTS", "localhost,127.0.0.1,::1").split(",") if h.strip()}
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, port)}
        except socket.gaierror as exc:
            raise UnsafeDestination("No se pudo resolver el host de destino.") from exc
    if not addresses:
        raise UnsafeDestination("El host no tiene direcciones de destino disponibles.")
    if any(not address.is_global for address in addresses) and host not in allowed_private:
        raise UnsafeDestination("El destino resuelve a una dirección privada; agréguelo a ALLOWED_PRIVATE_HOSTS si es una API autorizada.")


def check_api(url: str) -> dict:
    validate_destination(url)
    timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(url)
        return {"status_code": response.status_code, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": None, "error_message": None}
    except httpx.TimeoutException as exc:
        return {"status_code": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": "timeout", "error_message": str(exc) or "La solicitud excedió el tiempo límite."}
    except httpx.RequestError as exc:
        return {"status_code": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error_type": "connection", "error_message": str(exc)}

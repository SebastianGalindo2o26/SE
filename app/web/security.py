"""Protección de los formularios que modifican datos."""

import hmac
import secrets

from fastapi import Cookie, Form, HTTPException, Request

CSRF_COOKIE = "csrf_token"


def csrf_for_page(request: Request) -> tuple[str, bool]:
    token = request.cookies.get(CSRF_COOKIE)
    if token and len(token) >= 32:
        return token, False
    return secrets.token_urlsafe(32), True


def require_csrf(
    csrf_token: str | None = Form(None),
    csrf_cookie: str | None = Cookie(None, alias=CSRF_COOKIE),
) -> None:
    if not csrf_token or not csrf_cookie or not hmac.compare_digest(csrf_token, csrf_cookie):
        raise HTTPException(status_code=403, detail="Formulario no autorizado. Recargue la página e inténtelo de nuevo.")

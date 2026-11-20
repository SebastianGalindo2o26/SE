"""Ejecuta los casos C01-C08 contra una aplicación ya iniciada en localhost.

Uso: python -m scripts.validate_live --cleanup
"""

import argparse
from datetime import datetime, timezone

import httpx


BASE = "http://127.0.0.1:8000"
PREFIX = "Validación " + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
CREATED_IDS: list[int] = []


def create_api(client: httpx.Client, label: str, path: str, expected: int = 200, auth: dict[str, str] | None = None) -> int:
    name = f"{PREFIX} {label}"
    response = client.post(
        "/apis",
        data={"name": name, "url": BASE + path, "expected_status": expected, "interval_minutes": 10, "csrf_token": client.cookies["csrf_token"], **(auth or {})},
    )
    assert response.status_code == 303, f"No se pudo registrar {name}: {response.status_code} {response.text}"
    apis = client.get("/api/apis").json()
    api_id = next(api["id"] for api in apis if api["name"] == name)
    CREATED_IDS.append(api_id)
    return api_id


def check(client: httpx.Client, api_id: int, expected_rules: set[str], expected_severity: str) -> None:
    response = client.post(f"/apis/{api_id}/monitor", data={"csrf_token": client.cookies["csrf_token"]})
    assert response.status_code == 303, f"No se pudo monitorear {api_id}: {response.status_code} {response.text}"
    history = client.get("/api/history", params={"limit": 200}).json()
    latest = next(run for run in history if run["api_id"] == api_id)
    actual = {rule["id"] for rule in latest["rules"]}
    assert actual == expected_rules, f"API {api_id}: reglas {actual}; esperado {expected_rules}"
    assert latest["severity"] == expected_severity, f"API {api_id}: gravedad {latest['severity']}; esperado {expected_severity}"


def cleanup_created_apis() -> None:
    from app.infrastructure.database import SessionLocal
    from app.infrastructure.models import ApiEndpoint

    with SessionLocal() as db:
        for api_id in CREATED_IDS:
            api = db.get(ApiEndpoint, api_id)
            if api is not None and api.name.startswith(PREFIX):
                db.delete(api)
        db.commit()
    print(f"Limpieza: {len(CREATED_IDS)} APIs de esta validación eliminadas")


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida C01-C08 por HTTP contra el servidor local")
    parser.add_argument("--cleanup", action="store_true", help="Elimina de la base las APIs creadas por esta ejecución")
    args = parser.parse_args()
    try:
        run_cases()
    finally:
        if args.cleanup and CREATED_IDS:
            cleanup_created_apis()


def run_cases() -> None:
    with httpx.Client(base_url=BASE, trust_env=False, timeout=20, follow_redirects=False) as client:
        assert client.get("/health").json()["status"] == "ok", "Aplicación no disponible"
        client.get("/").raise_for_status()

        normal = create_api(client, "C01", "/demo/status/200")
        check(client, normal, {"R01"}, "normal")
        print("C01 OK: HTTP 200")

        server = create_api(client, "C02-C07", "/demo/status/500")
        check(client, server, {"R02"}, "media")
        print("C02 OK: un HTTP 500")

        auth = create_api(client, "C03", "/demo/status/401")
        check(client, auth, {"R06"}, "baja")
        print("C03 OK: HTTP 401")

        slow = create_api(client, "C04", "/demo/delay/2200")
        check(client, slow, {"R10"}, "baja")
        print("C04 OK: latencia alta")

        timeout = create_api(client, "C05", "/demo/delay/9000")
        check(client, timeout, {"R11"}, "media")
        print("C05 OK: timeout")

        unavailable = create_api(client, "C06", "/demo/status/503")
        check(client, unavailable, {"R04"}, "media")
        check(client, unavailable, {"R04"}, "media")
        check(client, unavailable, {"R04", "R12", "R14", "R15"}, "alta")
        print("C06 OK: tres HTTP 503")

        check(client, server, {"R02"}, "media")
        check(client, server, {"R02", "R12", "R13", "R15"}, "alta")
        print("C07 OK: tres HTTP 500")

    # La clave de este endpoint es pública y sirve solo para la demostración local.
    with httpx.Client(base_url=BASE, trust_env=False, timeout=20, follow_redirects=False) as client:
        client.get("/").raise_for_status()
        protected = create_api(client, "C08", "/demo/auth", auth={"auth_type": "api_key_header", "auth_header_name": "X-Demo-Key", "auth_secret": "sentinel-demo"})
        check(client, protected, {"R01"}, "normal")
        print("C08 OK: API key en header")
    print("C01-C08 completados correctamente")


if __name__ == "__main__":
    main()

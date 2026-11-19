"""Verifica la conexión configurada en .env sin imprimir credenciales."""

from sqlalchemy import inspect, text

from app.infrastructure.database import engine


def main() -> None:
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT 1")) != 1:
                raise RuntimeError("La base respondió un resultado inesperado.")
            tables = set(inspect(engine).get_table_names())
            if {"apis", "reglas", "monitoreos"}.issubset(tables):
                counts = {
                    "apis": connection.scalar(text("SELECT COUNT(*) FROM apis")),
                    "reglas": connection.scalar(text("SELECT COUNT(*) FROM reglas")),
                    "monitoreos": connection.scalar(text("SELECT COUNT(*) FROM monitoreos")),
                }
            else:
                counts = None
        print("Conexión a la base: OK")
        print("Tablas:", ", ".join(sorted(tables)) or "ninguna todavía")
        if counts:
            print("Registros:", ", ".join(f"{name}={count}" for name, count in counts.items()))
    except Exception as exc:
        print(f"Conexión a la base: ERROR ({type(exc).__name__})")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

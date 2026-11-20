"""Genera una clave Fernet local para cifrar tokens y API keys."""

import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values


def main() -> None:
    env_file = Path(".env")
    if not env_file.exists():
        env_file.write_bytes(Path(".env.example").read_bytes())
    if dotenv_values(env_file).get("CREDENTIALS_ENCRYPTION_KEY") or os.getenv("CREDENTIALS_ENCRYPTION_KEY"):
        print("La clave de cifrado ya está configurada.")
        return
    key = Fernet.generate_key()
    lines = env_file.read_bytes().splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip(b"\r\n") == b"CREDENTIALS_ENCRYPTION_KEY=":
            ending = line[len(line.rstrip(b"\r\n")):] or b"\n"
            lines[index] = b"CREDENTIALS_ENCRYPTION_KEY=" + key + ending
            env_file.write_bytes(b"".join(lines))
            break
    else:
        separator = b"" if env_file.read_bytes().endswith(b"\n") else b"\n"
        with env_file.open("ab") as stream:
            stream.write(separator + b"\n# Protege las credenciales de las APIs. Conserva esta clave si usas Neon en otro equipo.\n")
            stream.write(b"CREDENTIALS_ENCRYPTION_KEY=" + key + b"\n")
    print("Clave de cifrado creada en .env. Guárdala de forma segura para usar las mismas credenciales en otro equipo.")


if __name__ == "__main__":
    main()

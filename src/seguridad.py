"""
src/seguridad.py
Helpers de seguridad para el pipeline DataOps.

Provee funciones de cifrado simétrico (Fernet, AES-128 CBC + HMAC SHA-256)
y enmascaramiento, aplicadas sobre identificadores personales antes de la
carga al destino final.

Marco legal: Ley 19.628 sobre protección de la vida privada (Chile),
modernizada por la Ley 21.719 (2024). Ambas exigen tratamiento cifrado
o pseudonimizado de datos personales en reposo.
"""

import logging
import os
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carga las variables de .env (clave Fernet)
DIR_RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(DIR_RAIZ / ".env")

log = logging.getLogger("seguridad")

_CLAVE = os.getenv("FERNET_KEY")
if not _CLAVE:
    raise RuntimeError(
        "Falta FERNET_KEY en .env. Generala con: "
        'python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )

_fernet = Fernet(_CLAVE.encode() if isinstance(_CLAVE, str) else _CLAVE)


def cifrar(valor) -> str | None:
    """Cifra un valor con Fernet. NaN/None se mantiene como None."""
    if valor is None or pd.isna(valor):
        return None
    return _fernet.encrypt(str(valor).encode()).decode()


def descifrar(token: str) -> str:
    """Descifra un token Fernet. Útil para auditoría autorizada."""
    return _fernet.decrypt(token.encode()).decode()


def enmascarar(valor) -> str:
    """
    Enmascara un identificador para logs (U0042 → U***).
    Cumple el principio de mínimo dato visible.
    """
    if valor is None or pd.isna(valor) or str(valor) == "":
        return "***"
    s = str(valor)
    return s[0] + "***"
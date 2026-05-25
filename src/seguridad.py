"""
src/seguridad.py
Funciones simples para proteger datos personales.

En este proyecto se cifran los identificadores de usuario antes de
guardarlos en el archivo final. La clave se lee desde el archivo .env.
"""

import os
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet
from dotenv import load_dotenv

DIR_RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(DIR_RAIZ / ".env")

CLAVE = os.getenv("FERNET_KEY")
if not CLAVE:
    raise RuntimeError(
        "Falta FERNET_KEY en .env. Genera una clave y guardala antes de cargar datos."
    )

fernet = Fernet(CLAVE.encode())


def cifrar(valor) -> str | None:
    """Cifra un valor. Si viene vacio, queda como None."""
    if valor is None or pd.isna(valor):
        return None
    return fernet.encrypt(str(valor).encode()).decode()


def enmascarar(valor) -> str:
    """Oculta un identificador para que no aparezca completo en los logs."""
    if valor is None or pd.isna(valor) or str(valor) == "":
        return "***"
    return str(valor)[0] + "***"

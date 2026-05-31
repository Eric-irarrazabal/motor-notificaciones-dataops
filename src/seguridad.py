"""
src/seguridad.py
Funciones simples para proteger datos personales.

En este proyecto se cifran los identificadores de usuario (user_id y
source_user_id) antes de guardarlos. La clave se lee desde el archivo .env.

Usamos Fernet, una herramienta de la libreria cryptography. Cifra y
descifra con una misma clave secreta y detecta si el dato fue alterado.
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
    # Fernet trabaja con bytes: .encode() pasa el texto a bytes para cifrar,
    # y .decode() devuelve el resultado cifrado de vuelta como texto.
    return fernet.encrypt(str(valor).encode()).decode()


def enmascarar(valor) -> str:
    """Oculta un identificador para que no aparezca completo en los logs."""
    if valor is None or pd.isna(valor) or str(valor) == "":
        return "***"
    # Dejamos visible solo la primera letra y ocultamos el resto.
    return str(valor)[0] + "***"

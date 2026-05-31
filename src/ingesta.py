"""
src/ingesta.py
Etapa de ingesta.

Lee el CSV original, lo copia a data/raw/ y guarda un manifest con
informacion basica del archivo recibido.
"""

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

# Carpetas que usa esta etapa
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_FUENTE = DIR_RAIZ / "data" / "source"
DIR_CRUDOS = DIR_RAIZ / "data" / "raw"
DIR_LOGS = DIR_RAIZ / "logs"

# Log: a consola y a archivo
DIR_LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "ingesta.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ingesta")


def calcular_sha256(ruta: Path) -> str:
    """
    Calcula la huella SHA-256 del archivo.
    Sirve para comprobar que el archivo no cambio: si cambia una sola
    letra, el hash cambia por completo.
    """
    hasher = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        # Leemos el archivo por bloques de 8 KB en vez de cargarlo entero,
        # asi funciona igual aunque el archivo sea muy grande.
        while True:
            bloque = archivo.read(8192)
            if not bloque:        # se acabo el archivo
                break
            hasher.update(bloque)
    return hasher.hexdigest()


def contar_filas_csv(ruta: Path) -> int:
    """Cuenta las filas del CSV sin considerar el encabezado."""
    with open(ruta, encoding="utf-8") as archivo:
        return sum(1 for _ in archivo) - 1


def ingestar_csv(nombre_archivo: str = "02_notifications_raw_events.csv") -> dict:
    """
    Copia el archivo fuente a data/raw/ y genera un manifest.
    """
    ruta_fuente = DIR_FUENTE / nombre_archivo

    if not ruta_fuente.exists():
        log.error(f"Archivo fuente no encontrado: {ruta_fuente}")
        raise FileNotFoundError(f"No existe: {ruta_fuente}")

    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_crudo = f"notificaciones_{marca_tiempo}.csv"
    ruta_crudo = DIR_CRUDOS / nombre_crudo

    DIR_CRUDOS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ruta_fuente, ruta_crudo)

    hash_archivo = calcular_sha256(ruta_crudo)
    n_filas = contar_filas_csv(ruta_crudo)

    manifest = {
        "archivo_fuente": ruta_fuente.name,
        "archivo_crudo": ruta_crudo.name,
        "fecha_ingesta": datetime.now().isoformat(timespec="seconds"),
        "sha256": hash_archivo,
        "filas": n_filas,
        "etapa_pipeline": "ingesta",
    }

    ruta_manifest = DIR_CRUDOS / f"manifest_{marca_tiempo}.json"
    with open(ruta_manifest, "w", encoding="utf-8") as archivo:
        json.dump(manifest, archivo, indent=2, ensure_ascii=False)

    log.info(
        f"Ingesta OK | filas={n_filas} | sha256={hash_archivo[:12]} | "
        f"archivo={nombre_crudo}"
    )
    return manifest


if __name__ == "__main__":
    resultado = ingestar_csv()
    print("\n=== Resultado de la ingesta ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

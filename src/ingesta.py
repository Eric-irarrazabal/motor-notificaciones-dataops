"""
src/ingesta.py
Módulo de ingesta del pipeline DataOps híbrido.

Componente batch: lee el CSV fuente, lo copia a data/raw/
con marca de tiempo y genera un manifest JSON con SHA-256
para asegurar trazabilidad e idempotencia.
"""

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

# --- Configuración de rutas ---
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_FUENTE = DIR_RAIZ / "data" / "source"
DIR_CRUDOS = DIR_RAIZ / "data" / "raw"
DIR_LOGS = DIR_RAIZ / "logs"

# --- Configuración de logging ---
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
    """Calcula el hash SHA-256 de un archivo, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


def ingestar_csv(nombre_archivo: str = "02_notifications_raw_events.csv") -> dict:
    """
    Ingesta batch del CSV fuente.

    Pasos:
    1. Verifica que el archivo fuente exista.
    2. Copia el CSV a data/raw/ con timestamp en el nombre.
    3. Calcula SHA-256 de la copia.
    4. Genera un manifest JSON con metadatos de la ingesta.
    5. Devuelve un diccionario con el resultado para el orquestador.
    """
    ruta_fuente = DIR_FUENTE / nombre_archivo

    if not ruta_fuente.exists():
        log.error(f"Archivo fuente no encontrado: {ruta_fuente}")
        raise FileNotFoundError(f"No existe: {ruta_fuente}")

    # Timestamp para hacer cada copia única (idempotencia + auditoría)
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_crudo = f"notificaciones_{marca_tiempo}.csv"
    ruta_crudo = DIR_CRUDOS / nombre_crudo

    DIR_CRUDOS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ruta_fuente, ruta_crudo)

    # SHA-256 para trazabilidad inmutable
    hash_archivo = calcular_sha256(ruta_crudo)

    # Conteo rápido de filas sin cargar todo a memoria
    n_filas = sum(1 for _ in open(ruta_crudo, encoding="utf-8")) - 1  # -1 por el header

    # Manifest: prueba escrita de qué se ingestó y cuándo
    manifest = {
        "archivo_fuente": ruta_fuente.name,
        "archivo_crudo": ruta_crudo.name,
        "fecha_ingesta": datetime.now().isoformat(timespec="seconds"),
        "sha256": hash_archivo,
        "filas": n_filas,
        "etapa_pipeline": "ingesta",
    }
    ruta_manifest = DIR_CRUDOS / f"manifest_{marca_tiempo}.json"
    with open(ruta_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log.info(
        f"Ingesta batch OK | filas={n_filas} | sha256={hash_archivo[:12]} | "
        f"archivo={nombre_crudo}"
    )
    return manifest


if __name__ == "__main__":
    resultado = ingestar_csv()
    print("\n=== Resultado de la ingesta ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
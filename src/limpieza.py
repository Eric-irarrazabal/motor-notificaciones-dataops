"""
src/limpieza.py
Módulo de limpieza del pipeline DataOps.

Lee el último CSV crudo de data/raw/, aplica reglas de formato
(normalización, tipos, deduplicación) y guarda el resultado en
data/processed/. Las filas eliminadas (duplicadas o con timestamp
con formato imposible) se envían a data/rejected/ con su motivo.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

# --- Rutas ---
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_CRUDOS = DIR_RAIZ / "data" / "raw"
DIR_PROCESADOS = DIR_RAIZ / "data" / "processed"
DIR_RECHAZADOS = DIR_RAIZ / "data" / "rejected"
DIR_LOGS = DIR_RAIZ / "logs"

# --- Logging ---
DIR_LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "limpieza.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("limpieza")

# --- Constantes de dominio ---
CATEGORICAS_UPPER = [
    "event_type", "device", "delivery_channel",
    "priority", "status", "country",
]
MAPA_BOOL = {"true": True, "false": False, "1": True, "0": False}


def obtener_ultimo_crudo() -> Path:
    """Devuelve el CSV más reciente en data/raw/."""
    archivos = sorted(DIR_CRUDOS.glob("notificaciones_*.csv"))
    if not archivos:
        raise FileNotFoundError(
            "No hay archivos crudos en data/raw/. Ejecuta src/ingesta.py primero."
        )
    return archivos[-1]


def limpiar(ruta_crudo: Path | None = None) -> dict:
    """
    Aplica limpieza al CSV crudo y devuelve un diccionario con métricas.

    Reglas de limpieza:
    1. Quitar espacios (strip) en columnas string.
    2. Normalizar columnas categóricas a UPPER.
    3. Convertir 'seen' a booleano.
    4. Parsear 'created_at' a datetime (NaT si formato inválido).
    5. Convertir 'latency_ms' a numérico.
    6. Eliminar duplicados exactos por notification_id.
    7. Eliminar filas con timestamp con formato imposible.

    Las filas eliminadas se guardan en data/rejected/ con motivo.
    """
    if ruta_crudo is None:
        ruta_crudo = obtener_ultimo_crudo()

    log.info(f"Leyendo crudo: {ruta_crudo.name}")
    df = pd.read_csv(
        ruta_crudo,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    n_inicial = len(df)
    log.info(f"Filas iniciales: {n_inicial}")

    # 1. Strip de espacios en columnas string
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # 2. Normalizar categóricas a UPPER
    for col in CATEGORICAS_UPPER:
        if col in df.columns:
            df[col] = df[col].str.upper()

    # 3. Convertir 'seen' a booleano (los inválidos quedan en NaN)
    df["seen_bool"] = df["seen"].str.lower().map(MAPA_BOOL)
    n_seen_invalidos = df[df["seen"].notna() & df["seen_bool"].isna()].shape[0]

    # 4. Parsear created_at (NaT si formato imposible)
    df["created_at_dt"] = pd.to_datetime(
        df["created_at"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    # 5. latency_ms a numérico
    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")

    # --- Detección y separación de filas a rechazar ---

    # 6. Duplicados por notification_id (los vacíos no se consideran duplicados)
    mask_dup = (
        df.duplicated(subset=["notification_id"], keep="first")
        & df["notification_id"].notna()
    )
    rechazos_dup = df[mask_dup].copy()
    rechazos_dup["motivo_rechazo"] = "duplicado_notification_id"
    df = df[~mask_dup].copy()

    # 7. Timestamps con formato imposible (parseo falló pero el original NO estaba vacío)
    mask_ts = df["created_at"].notna() & df["created_at_dt"].isna()
    rechazos_ts = df[mask_ts].copy()
    rechazos_ts["motivo_rechazo"] = "timestamp_formato_invalido"
    df = df[~mask_ts].copy()

    # --- Guardar resultados ---
    DIR_PROCESADOS.mkdir(parents=True, exist_ok=True)
    DIR_RECHAZADOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    ruta_procesado = DIR_PROCESADOS / f"limpio_{marca}.csv"
    df.to_csv(ruta_procesado, index=False)

    rechazados_total = pd.concat(
        [rechazos_dup, rechazos_ts], ignore_index=True
    )
    if len(rechazados_total) > 0:
        ruta_rechazados = DIR_RECHAZADOS / f"rechazados_limpieza_{marca}.csv"
        rechazados_total.to_csv(ruta_rechazados, index=False)
        log.info(f"Rechazados de limpieza → {ruta_rechazados.name}")

    n_duplicados = len(rechazos_dup)
    n_ts_invalidos = len(rechazos_ts)
    n_final = len(df)

    # --- Métricas ---
    metricas = {
        "archivo_crudo": ruta_crudo.name,
        "archivo_procesado": ruta_procesado.name,
        "fecha_limpieza": datetime.now().isoformat(timespec="seconds"),
        "filas_inicial": int(n_inicial),
        "filas_final": int(n_final),
        "duplicados_eliminados": int(n_duplicados),
        "timestamps_invalidos_eliminados": int(n_ts_invalidos),
        "seen_invalidos_detectados": int(n_seen_invalidos),
        "etapa_pipeline": "limpieza",
    }
    ruta_metricas = DIR_PROCESADOS / f"metricas_{marca}.json"
    with open(ruta_metricas, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False)

    log.info(
        f"Limpieza OK | inicial={n_inicial} | final={n_final} | "
        f"dup={n_duplicados} | ts_invalidos={n_ts_invalidos} | "
        f"seen_invalidos={n_seen_invalidos}"
    )
    return metricas


if __name__ == "__main__":
    resultado = limpiar()
    print("\n=== Métricas de limpieza ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
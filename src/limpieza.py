"""
src/limpieza.py
Etapa de limpieza.

Lee el ultimo CSV de data/raw/, corrige formatos simples y separa las
filas que no se pueden seguir procesando.
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

CATEGORICAS_UPPER = [
    "event_type",
    "device",
    "delivery_channel",
    "priority",
    "status",
    "country",
]
MAPA_BOOL = {"true": True, "false": False, "1": True, "0": False}


def obtener_ultimo_crudo() -> Path:
    """Devuelve el archivo crudo mas reciente."""
    archivos = sorted(DIR_CRUDOS.glob("notificaciones_*.csv"))
    if not archivos:
        raise FileNotFoundError(
            "No hay archivos crudos en data/raw/. Ejecuta src/ingesta.py primero."
        )
    return archivos[-1]


def limpiar(ruta_crudo: Path | None = None) -> dict:
    """
    Limpia el CSV crudo y devuelve un resumen con metricas.

    Reglas aplicadas:
    1. Quitar espacios en textos.
    2. Pasar categorias a mayusculas.
    3. Convertir seen a booleano.
    4. Convertir created_at a fecha.
    5. Convertir latency_ms a numero.
    6. Quitar notification_id duplicados.
    7. Quitar fechas con formato invalido.
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

    # include=["object", "string"] cubre pandas 2.x (object) y pandas 3.x (string)
    # sin disparar el Pandas4Warning de cambio de comportamiento.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].str.strip()

    for col in CATEGORICAS_UPPER:
        if col in df.columns:
            df[col] = df[col].str.upper()

    df["seen_bool"] = df["seen"].str.lower().map(MAPA_BOOL)
    n_seen_invalidos = df[df["seen"].notna() & df["seen_bool"].isna()].shape[0]

    df["created_at_dt"] = pd.to_datetime(
        df["created_at"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")

    # Duplicados por notification_id. Los vacios se revisan en validacion.
    mask_dup = (
        df.duplicated(subset=["notification_id"], keep="first")
        & df["notification_id"].notna()
    )
    rechazos_dup = df[mask_dup].copy()
    rechazos_dup["motivo_rechazo"] = "duplicado_notification_id"
    df = df[~mask_dup].copy()

    # Fechas que no se pudieron convertir.
    mask_ts = df["created_at"].notna() & df["created_at_dt"].isna()
    rechazos_ts = df[mask_ts].copy()
    rechazos_ts["motivo_rechazo"] = "timestamp_formato_invalido"
    df = df[~mask_ts].copy()

    DIR_PROCESADOS.mkdir(parents=True, exist_ok=True)
    DIR_RECHAZADOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    ruta_procesado = DIR_PROCESADOS / f"limpio_{marca}.csv"
    df.to_csv(ruta_procesado, index=False)

    rechazados_total = pd.concat([rechazos_dup, rechazos_ts], ignore_index=True)
    if len(rechazados_total) > 0:
        ruta_rechazados = DIR_RECHAZADOS / f"rechazados_limpieza_{marca}.csv"
        rechazados_total.to_csv(ruta_rechazados, index=False)
        log.info(f"Rechazados de limpieza -> {ruta_rechazados.name}")

    n_duplicados = len(rechazos_dup)
    n_ts_invalidos = len(rechazos_ts)
    n_final = len(df)

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
    print("\n=== Metricas de limpieza ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

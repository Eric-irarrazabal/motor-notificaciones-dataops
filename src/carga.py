"""
src/carga.py
Etapa de carga del pipeline.

Toma los registros validos, cifra los ids de usuario y los guarda en
la tabla `notificaciones` de Supabase. Tambien mantiene una copia
local en data/validated/destino_final.csv como respaldo de auditoria.

Idempotencia: si una notification_id ya esta en Supabase, no se
inserta de nuevo (ON CONFLICT DO NOTHING). El conteo de insertadas
vs idempotentes queda en la tabla load_audit.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Permite ejecutar este archivo solo o desde pipeline.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seguridad import cifrar, enmascarar
from db import (
    ids_existentes,
    insertar_load_audit,
    insertar_notificaciones,
    contar_destino,
)

# Carpetas que usa esta etapa
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_VALIDADOS = DIR_RAIZ / "data" / "validated"
DIR_REPORTES = DIR_RAIZ / "data" / "reports"
DIR_LOGS = DIR_RAIZ / "logs"

DESTINO_FINAL_CSV = DIR_VALIDADOS / "destino_final.csv"
AUDITORIA_CSV = DIR_REPORTES / "load_audit.csv"

# Log: a consola y a archivo
DIR_LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "carga.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("carga")


def obtener_ultimos_validos() -> Path:
    archivos = sorted(DIR_VALIDADOS.glob("validos_*.csv"))
    if not archivos:
        raise FileNotFoundError(
            "No hay archivos validos en data/validated/. "
            "Ejecuta src/validacion.py primero."
        )
    return archivos[-1]


def cargar(ruta_validos: Path | None = None) -> dict:
    """Carga los datos validos a Supabase y al CSV local de respaldo."""
    if ruta_validos is None:
        ruta_validos = obtener_ultimos_validos()

    log.info(f"Leyendo validos: {ruta_validos.name}")
    df = pd.read_csv(ruta_validos)
    n_entrada = len(df)

    # 1. Cifrar identificadores antes de cargar (datos personales).
    log.info("Cifrando identificadores de usuario")
    df["user_id_enc"] = df["user_id"].apply(cifrar)
    df["source_user_id_enc"] = df["source_user_id"].apply(cifrar)

    if n_entrada > 0:
        ejemplo_user = enmascarar(df["user_id"].iloc[0])
        ejemplo_enc = df["user_id_enc"].iloc[0][:30] + "..."
        log.info(f"Ejemplo cifrado: {ejemplo_user} -> {ejemplo_enc}")

    # 2. Quitar las columnas en claro despues de cifrar.
    df = df.drop(columns=["user_id", "source_user_id"])

    # 3. Calcular cuantas filas son nuevas vs repetidas (idempotencia).
    log.info("Consultando notification_id existentes en Supabase")
    ids_actuales = df["notification_id"].astype(str).tolist()
    existentes = ids_existentes(ids_actuales)
    n_repetidos = sum(1 for nid in ids_actuales if nid in existentes)
    n_nuevos = n_entrada - n_repetidos
    log.info(f"Idempotencia | nuevos={n_nuevos} | repetidos={n_repetidos}")

    # 4. Insertar a Supabase (ON CONFLICT DO NOTHING evita duplicados).
    log.info("Insertando en Supabase...")
    filas = df.to_dict(orient="records")
    # pandas deja algunos valores en tipos que psycopg2 no entiende
    # (NaN, numpy.bool_, etc.), asi que los pasamos a tipos de Python.
    for fila in filas:
        # post_id y comment_id pueden venir como NaN (float). Los dejamos en None.
        for columna in ("post_id", "comment_id"):
            if columna in fila and (fila[columna] is None or pd.isna(fila[columna])):
                fila[columna] = None
        # seen puede venir como texto o como bool: lo dejamos en bool de Python.
        if "seen" in fila:
            if isinstance(fila["seen"], str):
                fila["seen"] = fila["seen"].lower() in ("true", "1")
            else:
                fila["seen"] = bool(fila["seen"])
        # latency_ms lo dejamos en entero (si no se puede, queda en 0).
        if "latency_ms" in fila and fila["latency_ms"] is not None:
            try:
                fila["latency_ms"] = int(float(fila["latency_ms"]))
            except (TypeError, ValueError):
                fila["latency_ms"] = 0
    insertar_notificaciones(filas)

    # 5. Confirmar total en destino consultando.
    total_destino = contar_destino()
    log.info(
        f"Carga OK | insertados={n_nuevos} | repetidos={n_repetidos} | "
        f"total_destino={total_destino}"
    )

    # 6. Respaldo local en CSV (copia de seguridad, ademas de lo que ya quedo en Supabase).
    DIR_VALIDADOS.mkdir(parents=True, exist_ok=True)
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)
    if DESTINO_FINAL_CSV.exists():
        existentes_csv = pd.read_csv(DESTINO_FINAL_CSV)
        ids_csv = set(existentes_csv["notification_id"].astype(str))
        nuevos_df = df[~df["notification_id"].astype(str).isin(ids_csv)]
        combinado = pd.concat([existentes_csv, nuevos_df], ignore_index=True)
    else:
        combinado = df
    combinado.to_csv(DESTINO_FINAL_CSV, index=False)

    # 7. Auditoria en tabla Supabase y en CSV local.
    registro_auditoria = {
        "archivo_origen": ruta_validos.name,
        "filas_entrada": n_entrada,
        "filas_insertadas": n_nuevos,
        "filas_idempotentes": n_repetidos,
        "total_destino": total_destino,
        "cifrado": "Fernet",
    }
    try:
        insertar_load_audit(registro_auditoria)
    except Exception as e:
        log.warning(f"No se pudo escribir load_audit en Supabase: {e}")

    # Respaldo de auditoria en CSV.
    registro_csv = dict(registro_auditoria)
    registro_csv["fecha_carga"] = datetime.now().isoformat(timespec="seconds")
    df_aud = pd.DataFrame([registro_csv])
    if AUDITORIA_CSV.exists():
        df_aud.to_csv(AUDITORIA_CSV, mode="a", header=False, index=False)
    else:
        df_aud.to_csv(AUDITORIA_CSV, index=False)

    return registro_csv


if __name__ == "__main__":
    resultado = cargar()
    print("\n=== Reporte de carga ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

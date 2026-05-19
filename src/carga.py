"""
src/carga.py
Módulo de carga del pipeline DataOps.

Toma los registros validados, cifra identificadores personales
(user_id, source_user_id) con Fernet, y los carga al destino final
(archivo CSV que simula la tabla notifications de la BD).

Garantías:
- Cifrado en reposo de PII (Ley 19.628 / 21.719).
- Idempotencia: re-ejecutar no duplica (clave: notification_id).
- Auditoría: cada carga deja registro en load_audit.csv.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

# Permitimos que carga.py funcione tanto suelto como dentro del orquestador
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seguridad import cifrar, enmascarar

# --- Rutas ---
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_VALIDADOS = DIR_RAIZ / "data" / "validated"
DIR_REPORTES = DIR_RAIZ / "data" / "reports"
DIR_LOGS = DIR_RAIZ / "logs"

DESTINO_FINAL = DIR_VALIDADOS / "destino_final.csv"
AUDITORIA = DIR_REPORTES / "load_audit.csv"

# --- Logging ---
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
            "No hay archivos válidos en data/validated/. "
            "Ejecuta src/validacion.py primero."
        )
    return archivos[-1]


def cargar(ruta_validos: Path | None = None) -> dict:
    """
    Carga los registros validados al destino final con:
    - Cifrado Fernet de user_id y source_user_id.
    - Idempotencia por notification_id.
    - Registro en auditoría.
    """
    if ruta_validos is None:
        ruta_validos = obtener_ultimos_validos()

    log.info(f"Leyendo válidos: {ruta_validos.name}")
    df = pd.read_csv(ruta_validos)
    n_entrada = len(df)

    # --- Cifrado de PII ---
    log.info("Cifrando identificadores con Fernet (AES-128)...")
    df["user_id_enc"] = df["user_id"].apply(cifrar)
    df["source_user_id_enc"] = df["source_user_id"].apply(cifrar)

    # Mostrar 1 ejemplo en logs ENMASCARADO (no filtra datos)
    if n_entrada > 0:
        ejemplo_user = enmascarar(df["user_id"].iloc[0])
        ejemplo_enc = df["user_id_enc"].iloc[0][:30] + "..."
        log.info(f"Ejemplo cifrado: {ejemplo_user} → {ejemplo_enc}")

    # Eliminar columnas en claro (cifrado en reposo)
    df = df.drop(columns=["user_id", "source_user_id"])

    # --- Idempotencia: comparar contra destino existente ---
    DIR_VALIDADOS.mkdir(parents=True, exist_ok=True)
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)

    if DESTINO_FINAL.exists():
        existentes = pd.read_csv(DESTINO_FINAL)
        ids_existentes = set(existentes["notification_id"].astype(str))
        nuevos = df[~df["notification_id"].astype(str).isin(ids_existentes)]
        n_idempotentes = n_entrada - len(nuevos)
        combinado = pd.concat([existentes, nuevos], ignore_index=True)
        log.info(
            f"Idempotencia | ya cargados={n_idempotentes} | "
            f"nuevos a insertar={len(nuevos)}"
        )
    else:
        nuevos = df
        n_idempotentes = 0
        combinado = df
        log.info("Primera carga: destino_final.csv no existía")

    n_insertados = len(nuevos)
    combinado.to_csv(DESTINO_FINAL, index=False)

    # --- Auditoría ---
    registro_auditoria = {
        "fecha_carga": datetime.now().isoformat(timespec="seconds"),
        "archivo_origen": ruta_validos.name,
        "filas_entrada": n_entrada,
        "filas_insertadas": n_insertados,
        "filas_idempotentes": n_idempotentes,
        "total_destino": len(combinado),
        "cifrado": "Fernet AES-128 CBC + HMAC SHA-256",
    }

    df_auditoria = pd.DataFrame([registro_auditoria])
    if AUDITORIA.exists():
        df_auditoria.to_csv(AUDITORIA, mode="a", header=False, index=False)
    else:
        df_auditoria.to_csv(AUDITORIA, index=False)

    log.info(
        f"Carga OK | insertados={n_insertados} | idempotentes={n_idempotentes} | "
        f"total_destino={len(combinado)} | cifrado=Fernet AES-128"
    )
    return registro_auditoria


if __name__ == "__main__":
    resultado = cargar()
    print("\n=== Reporte de carga ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
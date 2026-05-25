"""
src/carga.py
Etapa de carga del pipeline.

Toma los registros validos, cifra los ids de usuario y los guarda en
data/validated/destino_final.csv. Tambien evita cargar dos veces una
misma notificacion.
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
            "No hay archivos validos en data/validated/. "
            "Ejecuta src/validacion.py primero."
        )
    return archivos[-1]


def cargar(ruta_validos: Path | None = None) -> dict:
    """Carga los datos validos al archivo final."""
    if ruta_validos is None:
        ruta_validos = obtener_ultimos_validos()

    log.info(f"Leyendo validos: {ruta_validos.name}")
    df = pd.read_csv(ruta_validos)
    n_entrada = len(df)

    # Se cifran los ids porque son datos personales.
    log.info("Cifrando identificadores de usuario")
    df["user_id_enc"] = df["user_id"].apply(cifrar)
    df["source_user_id_enc"] = df["source_user_id"].apply(cifrar)

    if n_entrada > 0:
        ejemplo_user = enmascarar(df["user_id"].iloc[0])
        ejemplo_enc = df["user_id_enc"].iloc[0][:30] + "..."
        log.info(f"Ejemplo cifrado: {ejemplo_user} -> {ejemplo_enc}")

    # Despues de cifrar, no se guardan los ids originales.
    df = df.drop(columns=["user_id", "source_user_id"])

    DIR_VALIDADOS.mkdir(parents=True, exist_ok=True)
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)

    # Si ya existe el destino, se agregan solo las notificaciones nuevas.
    if DESTINO_FINAL.exists():
        existentes = pd.read_csv(DESTINO_FINAL)
        ids_existentes = set(existentes["notification_id"].astype(str))
        nuevos = df[~df["notification_id"].astype(str).isin(ids_existentes)]
        n_repetidos = n_entrada - len(nuevos)
        combinado = pd.concat([existentes, nuevos], ignore_index=True)
        log.info(
            f"Carga sin duplicar | repetidos={n_repetidos} | "
            f"nuevos={len(nuevos)}"
        )
    else:
        nuevos = df
        n_repetidos = 0
        combinado = df
        log.info("Primera carga: se crea destino_final.csv")

    n_insertados = len(nuevos)
    combinado.to_csv(DESTINO_FINAL, index=False)

    registro_auditoria = {
        "fecha_carga": datetime.now().isoformat(timespec="seconds"),
        "archivo_origen": ruta_validos.name,
        "filas_entrada": n_entrada,
        "filas_insertadas": n_insertados,
        "filas_idempotentes": n_repetidos,
        "total_destino": len(combinado),
        "cifrado": "Fernet",
    }

    df_auditoria = pd.DataFrame([registro_auditoria])
    if AUDITORIA.exists():
        df_auditoria.to_csv(AUDITORIA, mode="a", header=False, index=False)
    else:
        df_auditoria.to_csv(AUDITORIA, index=False)

    log.info(
        f"Carga OK | insertados={n_insertados} | repetidos={n_repetidos} | "
        f"total_destino={len(combinado)}"
    )
    return registro_auditoria


if __name__ == "__main__":
    resultado = cargar()
    print("\n=== Reporte de carga ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

"""
src/kpis.py
Módulo de KPIs operativos del pipeline DataOps.

Lee los reportes intermedios (limpieza, validación, carga) y el
destino final, calcula los 5 KPIs clave y los compara contra
los SLO definidos. Guarda el reporte en data/reports/kpis_latest.json.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

# --- Rutas ---
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_PROCESADOS = DIR_RAIZ / "data" / "processed"
DIR_VALIDADOS = DIR_RAIZ / "data" / "validated"
DIR_REPORTES = DIR_RAIZ / "data" / "reports"
DIR_LOGS = DIR_RAIZ / "logs"

DESTINO_FINAL = DIR_VALIDADOS / "destino_final.csv"

# --- Logging ---
DIR_LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "kpis.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("kpis")

# --- SLO objetivos ---
SLO = {
    "completitud_pct": 95.0,        # >= 95%
    "tasa_rechazo_pct": 15.0,       # <= 15%
    "cumplimiento_sla_pct": 85.0,   # >= 85%
    "latencia_promedio_ms": 10000,  # <= 10s
    "latencia_p95_ms": 30000,       # <= 30s
}

# Campos obligatorios para medir completitud
CAMPOS_OBLIGATORIOS = [
    "notification_id", "event_id", "event_type",
    "user_id_enc", "source_user_id_enc",
    "created_at", "device", "delivery_channel",
    "priority", "seen", "status", "country",
]


def _ultimo(patron: str, directorio: Path) -> Path | None:
    archivos = sorted(directorio.glob(patron))
    return archivos[-1] if archivos else None


def calcular_kpis() -> dict:
    """Calcula los 5 KPIs operativos y compara con los SLO."""
    if not DESTINO_FINAL.exists():
        raise FileNotFoundError(
            "No existe data/validated/destino_final.csv. Ejecuta src/carga.py primero."
        )

    log.info(f"Leyendo destino final: {DESTINO_FINAL.name}")
    df = pd.read_csv(DESTINO_FINAL)
    n_destino = len(df)

    # --- Reconstruir el total inicial a partir de los reportes intermedios ---
    metricas_lim = json.loads(_ultimo("metricas_*.json", DIR_PROCESADOS).read_text(encoding="utf-8"))
    reporte_val = json.loads(_ultimo("reporte_validacion_*.json", DIR_VALIDADOS).read_text(encoding="utf-8"))

    n_inicial = metricas_lim["filas_inicial"]
    n_eliminados_limpieza = (
        metricas_lim["duplicados_eliminados"]
        + metricas_lim["timestamps_invalidos_eliminados"]
    )
    n_rechazados_validacion = reporte_val["rechazados"]
    n_rechazados_total = n_eliminados_limpieza + n_rechazados_validacion

    # --- KPI 1: Completitud ---
    columnas_existentes = [c for c in CAMPOS_OBLIGATORIOS if c in df.columns]
    total_celdas = len(df) * len(columnas_existentes)
    celdas_no_nulas = df[columnas_existentes].notna().sum().sum()
    completitud_pct = (celdas_no_nulas / total_celdas * 100) if total_celdas else 0

    # --- KPI 2: Tasa de rechazo ---
    tasa_rechazo_pct = (n_rechazados_total / n_inicial * 100) if n_inicial else 0

    # --- KPI 3, 4, 5: SLA y latencias (solo sobre status=SENT) ---
    df_sent = df[df["status"] == "SENT"].copy()
    df_sent["latency_ms"] = pd.to_numeric(df_sent["latency_ms"], errors="coerce")
    df_sent_validas = df_sent.dropna(subset=["latency_ms"])

    cumplen_sla = df_sent_validas[df_sent_validas["latency_ms"] <= 30000]
    cumplimiento_sla_pct = (
        len(cumplen_sla) / len(df_sent_validas) * 100
        if len(df_sent_validas) else 0
    )

    latencia_promedio_ms = float(df_sent_validas["latency_ms"].mean()) if len(df_sent_validas) else 0
    latencia_p95_ms = float(df_sent_validas["latency_ms"].quantile(0.95)) if len(df_sent_validas) else 0

    # --- Construir reporte con SLO ---
    def cumple(valor, slo, mayor_es_mejor=True):
        return bool((valor >= slo) if mayor_es_mejor else (valor <= slo))

    kpis = {
        "fecha_calculo": datetime.now().isoformat(timespec="seconds"),
        "registros_destino": int(n_destino),
        "registros_inicial": int(n_inicial),
        "registros_rechazados_total": int(n_rechazados_total),
        "kpis": {
            "completitud_pct": {
                "valor": round(completitud_pct, 2),
                "slo": SLO["completitud_pct"],
                "cumple": cumple(completitud_pct, SLO["completitud_pct"], True),
            },
            "tasa_rechazo_pct": {
                "valor": round(tasa_rechazo_pct, 2),
                "slo": SLO["tasa_rechazo_pct"],
                "cumple": cumple(tasa_rechazo_pct, SLO["tasa_rechazo_pct"], False),
            },
            "cumplimiento_sla_pct": {
                "valor": round(cumplimiento_sla_pct, 2),
                "slo": SLO["cumplimiento_sla_pct"],
                "cumple": cumple(cumplimiento_sla_pct, SLO["cumplimiento_sla_pct"], True),
            },
            "latencia_promedio_ms": {
                "valor": round(latencia_promedio_ms, 2),
                "slo": SLO["latencia_promedio_ms"],
                "cumple": cumple(latencia_promedio_ms, SLO["latencia_promedio_ms"], False),
            },
            "latencia_p95_ms": {
                "valor": round(latencia_p95_ms, 2),
                "slo": SLO["latencia_p95_ms"],
                "cumple": cumple(latencia_p95_ms, SLO["latencia_p95_ms"], False),
            },
        },
        "errores_por_etapa": {
            "ingesta": 0,
            "limpieza": int(n_eliminados_limpieza),
            "validacion": int(n_rechazados_validacion),
            "carga": 0,
        },
    }

    # --- Guardar ---
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    ruta_latest = DIR_REPORTES / "kpis_latest.json"
    ruta_versionado = DIR_REPORTES / f"kpis_{marca}.json"

    for ruta in (ruta_latest, ruta_versionado):
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(kpis, f, indent=2, ensure_ascii=False)

    # --- Log resumen ---
    alertas = sum(1 for k, v in kpis["kpis"].items() if not v["cumple"])
    estado = "TODOS DENTRO DE SLO" if alertas == 0 else f"{alertas} ALERTA(S)"
    log.info(
        f"KPIs OK | completitud={completitud_pct:.1f}% | "
        f"rechazo={tasa_rechazo_pct:.1f}% | "
        f"sla={cumplimiento_sla_pct:.1f}% | "
        f"p95={latencia_p95_ms:.0f}ms | {estado}"
    )
    return kpis


if __name__ == "__main__":
    resultado = calcular_kpis()
    print("\n=== KPIs del pipeline ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
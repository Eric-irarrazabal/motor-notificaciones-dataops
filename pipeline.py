"""
pipeline.py
Orquestador del pipeline DataOps híbrido modular.

Ejecuta las 5 etapas en secuencia y produce un resumen ejecutivo
con métricas y KPIs. Único punto de entrada para la demo:
    python pipeline.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# --- Setup ANTES de importar los módulos ---
DIR_RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_RAIZ / "src"))

DIR_LOGS = DIR_RAIZ / "logs"
DIR_LOGS.mkdir(parents=True, exist_ok=True)

# Logger del orquestador (este es el primero, gana basicConfig)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "orquestador.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("orquestador")

# Ahora sí, importamos las etapas
from ingesta import ingestar_csv
from limpieza import limpiar
from validacion import validar
from carga import cargar
from kpis import calcular_kpis


def main():
    log.info("=" * 64)
    log.info("PIPELINE DATAOPS HÍBRIDO MODULAR — INICIANDO")
    log.info("=" * 64)

    inicio = datetime.now()

    try:
        # --- ETAPA 1: INGESTA ---
        log.info(">>> ETAPA 1/5: INGESTA")
        manifest = ingestar_csv()

        # --- ETAPA 2: LIMPIEZA ---
        log.info(">>> ETAPA 2/5: LIMPIEZA")
        metricas_lim = limpiar()

        # --- ETAPA 3: VALIDACIÓN ---
        log.info(">>> ETAPA 3/5: VALIDACIÓN")
        reporte_val = validar()

        # --- ETAPA 4: CARGA ---
        log.info(">>> ETAPA 4/5: CARGA")
        auditoria = cargar()

        # --- ETAPA 5: KPIs ---
        log.info(">>> ETAPA 5/5: KPIs")
        kpis = calcular_kpis()

        # --- RESUMEN EJECUTIVO ---
        duracion = (datetime.now() - inicio).total_seconds()
        dropped_limpieza = (
            metricas_lim["duplicados_eliminados"]
            + metricas_lim["timestamps_invalidos_eliminados"]
        )

        log.info("=" * 64)
        log.info("RESUMEN EJECUTIVO")
        log.info("=" * 64)
        log.info(
            f"Ingesta    | filas={manifest['filas']} | "
            f"sha256={manifest['sha256'][:12]}"
        )
        log.info(
            f"Limpieza   | inicial={metricas_lim['filas_inicial']} | "
            f"final={metricas_lim['filas_final']} | "
            f"descartadas={dropped_limpieza}"
        )
        log.info(
            f"Validacion | validos={reporte_val['validos']}/{reporte_val['total']} "
            f"({reporte_val['porcentaje_validos']}%) | "
            f"rechazados={reporte_val['rechazados']}"
        )
        log.info(
            f"Carga      | insertados={auditoria['filas_insertadas']} | "
            f"idempotentes={auditoria['filas_idempotentes']} | "
            f"total_destino={auditoria['total_destino']}"
        )

        cumplen = sum(1 for v in kpis["kpis"].values() if v["cumple"])
        log.info(f"KPIs       | {cumplen}/5 dentro de SLO")
        for nombre, kpi in kpis["kpis"].items():
            marca = "[OK]" if kpi["cumple"] else "[!!]"
            log.info(f"             {marca} {nombre}: {kpi['valor']} (SLO: {kpi['slo']})")

        log.info("-" * 64)
        log.info(f"Duracion total: {duracion:.2f}s")
        log.info("=" * 64)
        log.info("PIPELINE OK")
        log.info("=" * 64)

    except Exception as e:
        log.exception(f"PIPELINE FALLO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
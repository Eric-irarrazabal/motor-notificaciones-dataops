"""
pipeline.py
Archivo principal para ejecutar el pipeline completo.

Corre las etapas en orden:
1. Ingesta
2. Limpieza
3. Validacion
4. Carga
5. KPIs
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

DIR_RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_RAIZ / "src"))

DIR_LOGS = DIR_RAIZ / "logs"
DIR_LOGS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "orquestador.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pipeline_notificaciones")

# Importamos las etapas despues de agregar src/ al sys.path
# Python las encuentra tanto al correr "python pipeline.py" como al ejecutar cada etapa por separado.
from carga import cargar
from ingesta import ingestar_csv
from kpis import calcular_kpis
from limpieza import limpiar
from validacion import validar


def main():
    log.info("INICIANDO PIPELINE DE NOTIFICACIONES - ")

    inicio = datetime.now()

    try:
        log.info("ETAPA 1/5: INGESTA")
        manifest = ingestar_csv()

        log.info("ETAPA 2/5: LIMPIEZA")
        metricas_lim = limpiar()

        log.info("ETAPA 3/5: VALIDACION")
        reporte_val = validar()

        log.info("ETAPA 4/5: CARGA")
        auditoria = cargar()

        log.info("ETAPA 5/5: KPIs")
        kpis = calcular_kpis()

        duracion = (datetime.now() - inicio).total_seconds()
        descartadas_limpieza = (
            metricas_lim["duplicados_eliminados"]
            + metricas_lim["timestamps_invalidos_eliminados"]
        )

        log.info("RESUMEN DEL PROCESO")
        log.info(
            f"Ingesta    | filas={manifest['filas']} | "
            f"sha256={manifest['sha256'][:12]}"
        )
        log.info(
            f"Limpieza   | inicial={metricas_lim['filas_inicial']} | "
            f"final={metricas_lim['filas_final']} | "
            f"descartados={descartadas_limpieza}"
        )
        log.info(
            f"Validacion | validos={reporte_val['validos']}/{reporte_val['total']} "
            f"({reporte_val['porcentaje_validos']}%) | "
            f"rechazados={reporte_val['rechazados']}"
        )
        log.info(
            f"Carga      | insertados={auditoria['filas_insertadas']} | "
            f"repetidos={auditoria['filas_idempotentes']} | "
            f"total_destino={auditoria['total_destino']}"
        )

        cumplen = sum(1 for indicador in kpis["kpis"].values() if indicador["cumple"])
        log.info(f"KPIs       | {cumplen}/5 dentro de la meta")

        nombres_kpi = {
            "completitud_pct": "Completitud de datos (%)",
            "tasa_rechazo_pct": "Tasa de rechazo (%)",
            "cumplimiento_sla_pct": "Cumplimiento SLA (%)",
            "latencia_promedio_ms": "Latencia promedio (ms)",
            "latencia_p95_ms": "Latencia P95 (ms)",
        }
        for nombre, kpi in kpis["kpis"].items():
            etiqueta = nombres_kpi.get(nombre, nombre)
            marca = "[OK]" if kpi["cumple"] else "[ALERTA]"
            log.info(f"             {marca} {etiqueta}: {kpi['valor']} (meta: {kpi['slo']})")

        log.info("-" * 64)
        log.info(f"Duracion total: {duracion:.2f}s")
        log.info("PIPELINE FUNCIONÓ CORRECTAMENTE")

    except Exception as error:
        log.exception(f"PIPELINE FALLÓ: {error}")
        sys.exit(1)


if __name__ == "__main__":  
    main()

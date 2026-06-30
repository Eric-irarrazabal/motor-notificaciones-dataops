
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

proceso = psutil.Process(os.getpid())


def contar_filas(resultado):
    if isinstance(resultado, dict):
        for clave in ("filas", "total", "filas_entrada", "registros_destino"):
            if clave in resultado:
                return resultado[clave]
    return None


def medir_etapa(nombre, funcion):
    proceso.cpu_percent(None)                          # reiniciamos el contador de CPU
    inicio = time.perf_counter()
    filas = None
    error = None
    try:
        filas = contar_filas(funcion())
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    segundos = time.perf_counter() - inicio
    cpu = proceso.cpu_percent(None)                    # CPU% usado durante la etapa
    ram = proceso.memory_info().rss / (1024 * 1024)    # RAM en MB
    return {
        "etapa": nombre,
        "segundos": round(segundos, 3),
        "cpu_pct": round(cpu, 1),
        "ram_mb": round(ram, 1),
        "filas": filas,
        "error": error,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entorno", default="local", help="local | docker | render")
    entorno = parser.parse_args().entorno

    salida = RAIZ / "data" / "reports"
    salida.mkdir(parents=True, exist_ok=True)

    # importamos las etapas del pipeline
    from ingesta import ingestar_csv
    from limpieza import limpiar
    from validacion import validar
    etapas = [("ingesta", ingestar_csv), ("limpieza", limpiar), ("validacion", validar)]
    try:
        from carga import cargar
        from kpis import calcular_kpis
        etapas += [("carga", cargar), ("kpis", calcular_kpis)]
    except Exception as e:
        print("Aviso: no se importaron carga/kpis (¿falta FERNET_KEY o DATABASE_URL?):", e)

    resultados = []
    inicio_total = time.perf_counter()
    for nombre, funcion in etapas:
        print("Midiendo", nombre, "...")
        r = medir_etapa(nombre, funcion)
        resultados.append(r)
        if r["error"]:
            print("  ", nombre, "ERROR ->", r["error"])
        else:
            print("  ", nombre, f"{r['segundos']}s | CPU {r['cpu_pct']}% | RAM {r['ram_mb']}MB")
    tiempo_total = round(time.perf_counter() - inicio_total, 3)

    filas = next((r["filas"] for r in resultados if r["etapa"] == "ingesta" and r["filas"]), 2000)
    throughput = round(filas / tiempo_total, 1) if tiempo_total else 0

    reporte = {
        "entorno": entorno,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "filas": filas,
        "tiempo_total_s": tiempo_total,
        "throughput_filas_s": throughput,
        "etapas": resultados,
        "errores": [r["etapa"] for r in resultados if r["error"]],
    }
    ruta_json = salida / f"perf_{entorno}.json"
    ruta_json.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nGuardado", ruta_json)

    # gráfico de tiempo por etapa
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ok = [r for r in resultados if not r["error"]]
        plt.figure(figsize=(7, 4))
        plt.bar([r["etapa"] for r in ok], [r["segundos"] for r in ok], color="#2c7fb8")
        plt.ylabel("segundos")
        plt.title(f"Tiempo por etapa ({entorno}) - total {tiempo_total}s")
        plt.tight_layout()
        plt.savefig(salida / f"perf_{entorno}.png")
        print("Guardado", salida / f"perf_{entorno}.png")
    except Exception as e:
        print("No se pudo graficar:", e)

    # tabla resumen
    print(f"\n=== Resumen {entorno} ===")
    print(f"{'etapa':12s} {'seg':>8s} {'CPU%':>7s} {'RAM MB':>8s}  error")
    for r in resultados:
        print(f"{r['etapa']:12s} {r['segundos']:>8} {r['cpu_pct']:>7} {r['ram_mb']:>8}  {r['error'] or ''}")
    print(f"TOTAL {tiempo_total}s | throughput {throughput} filas/s")


if __name__ == "__main__":
    main()

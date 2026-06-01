"""
scripts/reset_demo.py
Deja el proyecto como recien empezado, para hacer una demo limpia.

Hace dos cosas:
  1. Borra los archivos que dejaron las corridas anteriores
     (data/raw, processed, validated, rejected, reports y logs).
     NO toca data/source ni el codigo.
  2. Vacia las 3 tablas de Supabase (notificaciones, rechazados, load_audit).

Uso:
    python scripts/reset_demo.py

Despues de correrlo, "python pipeline.py" arranca como si fuera la primera vez:
la primera corrida inserta todo, y una segunda corrida muestra la idempotencia
(insertados = 0, repetidos = 1700).
"""

import sys
from pathlib import Path

DIR_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIR_RAIZ / "src"))

# Reutiliza la misma conexion que usa el resto del proyecto (lee DATABASE_URL del .env).
from db import conectar

# Carpetas a limpiar: se borran los archivos de adentro, las carpetas se conservan.
CARPETAS_LIMPIAR = [
    DIR_RAIZ / "data" / "raw",
    DIR_RAIZ / "data" / "processed",
    DIR_RAIZ / "data" / "validated",
    DIR_RAIZ / "data" / "rejected",
    DIR_RAIZ / "data" / "reports",
    DIR_RAIZ / "logs",
]


def limpiar_archivos() -> int:
    """Borra los archivos generados por corridas anteriores."""
    total = 0
    for carpeta in CARPETAS_LIMPIAR:
        if not carpeta.exists():
            continue
        for archivo in carpeta.iterdir():
            # Conserva .gitkeep por si se usa para versionar la carpeta vacia.
            if archivo.is_file() and archivo.name != ".gitkeep":
                archivo.unlink()
                total += 1
    return total


def vaciar_supabase() -> None:
    """Vacia las 3 tablas de Supabase y reinicia los contadores."""
    con = conectar()
    try:
        cur = con.cursor()
        # TRUNCATE borra todas las filas de las 3 tablas de una vez.
        # RESTART IDENTITY reinicia los id serial de rechazados y load_audit.
        cur.execute(
            "truncate table notificaciones, rechazados, load_audit restart identity;"
        )
        con.commit()
        cur.close()
    finally:
        con.close()


if __name__ == "__main__":
    print("=== RESET PARA DEMO LIMPIA ===")

    borrados = limpiar_archivos()
    print(f"Archivos locales borrados: {borrados}")

    try:
        vaciar_supabase()
        print("Tablas de Supabase vaciadas: notificaciones, rechazados, load_audit")
    except Exception as e:
        print(f"AVISO: no se pudo vaciar Supabase: {e}")
        print("Revisa que DATABASE_URL este en .env y que haya conexion a internet.")

    print("")
    print("Listo. El proyecto quedo en cero.")
    print("Ahora corre:  python pipeline.py")
    print("(Corre el pipeline una vez para ver la carga, y una segunda vez")
    print(" para ver la idempotencia: insertados=0, repetidos=1700.)")

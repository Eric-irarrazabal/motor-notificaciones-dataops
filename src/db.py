"""
src/db.py
Funciones simples para conectarse a Supabase (PostgreSQL).

Centraliza la conexion para que las etapas de carga, limpieza y
validacion puedan reutilizarla sin repetir codigo.

La cadena de conexion se lee desde la variable de entorno DATABASE_URL
que vive en el archivo .env. Si no existe, la funcion conectar() lanza
un error claro.
"""

import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

DIR_RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(DIR_RAIZ / ".env")


def conectar():
    """Devuelve una conexion abierta a Supabase. Falla con mensaje claro
    si no hay DATABASE_URL definida en .env."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL en .env. "
            "Copiala desde Supabase -> Project Settings -> Database -> Connection pooler."
        )
    return psycopg2.connect(url, connect_timeout=15)


def insertar_notificaciones(filas: list[dict]) -> int:
    """
    Inserta una lista de filas en la tabla notificaciones.

    si una notification_id ya existe en la tabla, esa fila se ignora y no se
    duplica. Eso es lo que hace que la carga sea idempotente, es decir,
    que se pueda volver a correr sin crear datos repetidos.

    El conteo exacto de filas nuevas vs repetidas NO se calcula aqui:
    lo hace carga.py ANTES de insertar, comparando con ids_existentes().

    Devuelve cuantas filas se enviaron a insertar.
    """
    if not filas:
        return 0

    sql = """
        insert into notificaciones (
            notification_id, event_id, event_type,
            user_id_enc, source_user_id_enc,
            post_id, comment_id, created_at,
            device, delivery_channel, priority,
            seen, status, app_version, country, latency_ms
        ) values (
            %(notification_id)s, %(event_id)s, %(event_type)s,
            %(user_id_enc)s, %(source_user_id_enc)s,
            %(post_id)s, %(comment_id)s, %(created_at)s,
            %(device)s, %(delivery_channel)s, %(priority)s,
            %(seen)s, %(status)s, %(app_version)s, %(country)s, %(latency_ms)s
        )
        on conflict (notification_id) do nothing
    """

    con = conectar()
    try:
        cur = con.cursor()
        # execute_batch envia las filas agrupadas (de a 200) en vez de una
        # por una, asi la insercion es mas rapida.
        psycopg2.extras.execute_batch(cur, sql, filas, page_size=200)
        con.commit()
        cur.close()
    finally:
        con.close()

    return len(filas)


def ids_existentes(notification_ids: list[str]) -> set[str]:
    """Devuelve el conjunto de notification_id que ya estan en Supabase."""
    if not notification_ids:
        return set()
    con = conectar()
    try:
        cur = con.cursor()
        cur.execute(
            "select notification_id from notificaciones where notification_id = any(%s)",
            (notification_ids,),
        )
        existentes = {r[0] for r in cur.fetchall()}
        cur.close()
    finally:
        con.close()
    return existentes


def insertar_rechazados(filas_con_motivo: list[dict], etapa: str) -> int:
    """
    Inserta filas rechazadas en la tabla rechazados.

    Cada fila debe traer la columna 'motivo_rechazo'.
    El resto del diccionario se serializa como JSON en payload_original.

    Devuelve cantidad de filas insertadas.
    """
    if not filas_con_motivo:
        return 0
    if etapa not in ("limpieza", "validacion"):
        raise ValueError(f"etapa invalida: {etapa}")

    sql = """
        insert into rechazados (notification_id, etapa, motivo_rechazo, payload_original)
        values (%s, %s, %s, %s)
    """

    con = conectar()
    try:
        cur = con.cursor()
        for fila in filas_con_motivo:
            motivo = fila.get("motivo_rechazo", "sin motivo")
            nid = fila.get("notification_id")
            # Limpiar payload (sacar valores que JSON no soporta).
            payload = {
                k: (str(v) if v is not None else None) for k, v in fila.items()
            }
            cur.execute(sql, (nid or None, etapa, motivo, json.dumps(payload)))
        con.commit()
        cur.close()
    finally:
        con.close()
    return len(filas_con_motivo)


def insertar_load_audit(registro: dict) -> None:
    """Inserta una fila en load_audit con los datos de la corrida."""
    sql = """
        insert into load_audit (
            archivo_origen, filas_entrada, filas_insertadas,
            filas_idempotentes, total_destino, cifrado
        ) values (
            %(archivo_origen)s, %(filas_entrada)s, %(filas_insertadas)s,
            %(filas_idempotentes)s, %(total_destino)s, %(cifrado)s
        )
    """
    con = conectar()
    try:
        cur = con.cursor()
        cur.execute(sql, registro)
        con.commit()
        cur.close()
    finally:
        con.close()


def contar_destino() -> int:
    """Cuantas filas tiene la tabla notificaciones."""
    con = conectar()
    try:
        cur = con.cursor()
        cur.execute("select count(*) from notificaciones")
        total = cur.fetchone()[0]
        cur.close()
    finally:
        con.close()
    return total

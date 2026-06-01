"""
scripts/generar_dataset.py
Genera un dataset sintetico de notificaciones de red social.

Total: 2000 filas
- 1700 filas validas
- 300 filas con anomalias inyectadas, repartidas en cuatro categorias:
    A) Estructurales (75): duplicados, timestamps invalidos, ids vacios.
    B) Dominio (115): valores fuera de los conjuntos permitidos.
    C) Logicas basicas (70): self-events, latencias negativas, fechas futuras.
    D) Reglas de negocio NUEVAS (40): horario nocturno para EMAIL,
       FOLLOW con prioridad HIGH, SENT con app_version vieja, eventos
       de tipo LIKE/COMMENT sin post_id.

El script usa una semilla fija (random.seed(42)) para que el dataset sea
reproducible: ejecutarlo dos veces produce el mismo archivo.

Salida:
    data/source/02_notifications_raw_events.csv  (el dataset de 2000 filas)
    metadata/03_anomalias_inyectadas_v2.json     (catalogo de anomalias)
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------------
# CONFIGURACION
# ----------------------------------------------------------------------

random.seed(42)

DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_SOURCE = DIR_RAIZ / "data" / "source"
DIR_METADATA = DIR_RAIZ / "metadata"

ARCHIVO_DATASET = DIR_SOURCE / "02_notifications_raw_events.csv"
ARCHIVO_ANOMALIAS = DIR_METADATA / "03_anomalias_inyectadas_v2.json"

# Dominios validos del caso de estudio.
EVENTOS = ["LIKE", "COMMENT", "FOLLOW"]
DEVICES = ["MOBILE", "WEB"]
CHANNELS = ["PUSH", "EMAIL", "IN_APP"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH"]
STATUSES = ["SENT", "PENDING", "FAILED"]
COUNTRIES = ["CL", "AR", "PE", "MX"]
APP_VERSIONS_VALIDAS = ["1.0.0", "1.1.0", "1.2.0", "2.0.0"]
APP_VERSIONS_VIEJAS = ["0.0.0", "0.9.0"]

# Cantidades.
N_VALIDAS = 1700
N_ANOMALIAS = 300

# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------


def id_usuario(n: int) -> str:
    return f"U{n:04d}"


def id_post(n: int) -> str:
    return f"P{n:04d}"


def id_comment(n: int) -> str:
    return f"C{n:05d}"


def fecha_aleatoria_horario_laboral() -> datetime:
    """Devuelve una fecha entre 8am y 22pm de algun dia de los ultimos 30."""
    ahora = datetime(2026, 5, 7, 12, 0, 0)
    dias_atras = random.randint(0, 30)
    hora = random.randint(8, 21)
    minuto = random.randint(0, 59)
    segundo = random.randint(0, 59)
    base = ahora - timedelta(days=dias_atras)
    return base.replace(hour=hora, minute=minuto, second=segundo)


def fecha_aleatoria_nocturna() -> datetime:
    """Devuelve una fecha entre 23pm y 7am (fuera de horario)."""
    ahora = datetime(2026, 5, 7, 12, 0, 0)
    dias_atras = random.randint(0, 30)
    hora = random.choice([23, 0, 1, 2, 3, 4, 5, 6])
    minuto = random.randint(0, 59)
    segundo = random.randint(0, 59)
    base = ahora - timedelta(days=dias_atras)
    return base.replace(hour=hora, minute=minuto, second=segundo)


def latencia_normal() -> int:
    """Latencia tipica en milisegundos."""
    return random.randint(200, 25000)


# ----------------------------------------------------------------------
# GENERADOR BASE
# ----------------------------------------------------------------------


def generar_fila_valida(n: int) -> dict:
    """Genera una fila completamente valida segun todas las reglas."""
    event_type = random.choice(EVENTOS)
    user_id = id_usuario(random.randint(1, 200))
    source_user_id = id_usuario(random.randint(1, 200))
    while source_user_id == user_id:
        source_user_id = id_usuario(random.randint(1, 200))

    # post_id obligatorio para LIKE y COMMENT, vacio para FOLLOW.
    if event_type in ("LIKE", "COMMENT"):
        post_id = id_post(random.randint(1, 50))
    else:
        post_id = ""

    # comment_id solo para COMMENT.
    comment_id = id_comment(n) if event_type == "COMMENT" else ""

    delivery_channel = random.choice(CHANNELS)

    # Regla de negocio nueva: EMAIL solo se manda en horario laboral.
    if delivery_channel == "EMAIL":
        created_at = fecha_aleatoria_horario_laboral()
    else:
        # PUSH e IN_APP pueden ser a cualquier hora.
        created_at = fecha_aleatoria_horario_laboral()

    # Regla de negocio nueva: FOLLOW no puede tener prioridad HIGH.
    if event_type == "FOLLOW":
        priority = random.choice(["LOW", "MEDIUM"])
    else:
        priority = random.choice(PRIORITIES)

    return {
        "notification_id": f"N{n:05d}",
        "event_id": f"E{n:05d}",
        "event_type": event_type,
        "user_id": user_id,
        "source_user_id": source_user_id,
        "post_id": post_id,
        "comment_id": comment_id,
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "device": random.choice(DEVICES),
        "delivery_channel": delivery_channel,
        "priority": priority,
        "seen": random.choice(["true", "false"]),
        "status": random.choice(STATUSES),
        "app_version": random.choice(APP_VERSIONS_VALIDAS),
        "country": random.choice(COUNTRIES),
        "latency_ms": latencia_normal(),
    }


# ----------------------------------------------------------------------
# INYECTORES DE ANOMALIAS
# ----------------------------------------------------------------------


def inyectar_duplicado(fila: dict, otra_fila: dict) -> dict:
    """Reemplaza notification_id por el de otra_fila."""
    fila["notification_id"] = otra_fila["notification_id"]
    return fila


def inyectar_timestamp_invalido(fila: dict) -> dict:
    formatos_imposibles = [
        "2026/13/40 99:99:99",
        "32/05/2026 25:00:00",
        "fecha-invalida",
        "2026-99-99 99:99:99",
        "00-00-0000 00:00:00",
    ]
    fila["created_at"] = random.choice(formatos_imposibles)
    return fila


def inyectar_id_vacio(fila: dict) -> dict:
    fila["notification_id"] = ""
    return fila


def inyectar_event_type_invalido(fila: dict) -> dict:
    fila["event_type"] = random.choice(["SHARE", "RETWEET", "LOVE", "REPOST", "DM"])
    return fila


def inyectar_device_invalido(fila: dict) -> dict:
    fila["device"] = random.choice(
        ["SMART_TV", "SMARTWATCH", "TABLET", "IOS", "ANDROID"]
    )
    return fila


def inyectar_channel_invalido(fila: dict) -> dict:
    fila["delivery_channel"] = random.choice(
        ["SMS", "WHATSAPP", "PHONE", "FAX", "TELEGRAM"]
    )
    return fila


def inyectar_priority_invalida(fila: dict) -> dict:
    fila["priority"] = random.choice(["URGENT", "CRITICAL", "NONE", "VERY_LOW"])
    return fila


def inyectar_status_invalido(fila: dict) -> dict:
    fila["status"] = random.choice(["UNKNOWN", "DELIVERED", "RETRY", "QUEUED"])
    return fila


def inyectar_country_invalido(fila: dict) -> dict:
    fila["country"] = random.choice(["US", "BR", "ES", "CO", "VE", "EC"])
    return fila


def inyectar_self_event(fila: dict) -> dict:
    fila["source_user_id"] = fila["user_id"]
    return fila


def inyectar_latencia_negativa(fila: dict) -> dict:
    fila["latency_ms"] = -random.randint(100, 5000)
    return fila


def inyectar_fecha_futura(fila: dict) -> dict:
    futuro = datetime(2027, random.randint(1, 12), random.randint(1, 28), 12, 0, 0)
    fila["created_at"] = futuro.strftime("%Y-%m-%d %H:%M:%S")
    return fila


def inyectar_horario_nocturno_email(fila: dict) -> dict:
    """Regla de negocio nueva: EMAIL no se envia entre 23:00 y 07:00."""
    fila["delivery_channel"] = "EMAIL"
    fila["created_at"] = fecha_aleatoria_nocturna().strftime("%Y-%m-%d %H:%M:%S")
    return fila


def inyectar_follow_high_priority(fila: dict) -> dict:
    """Regla de negocio nueva: FOLLOW no puede tener priority HIGH."""
    fila["event_type"] = "FOLLOW"
    fila["priority"] = "HIGH"
    fila["post_id"] = ""
    fila["comment_id"] = ""
    return fila


def inyectar_sent_version_vieja(fila: dict) -> dict:
    """Regla de negocio nueva: status SENT no acepta app_version vieja."""
    fila["status"] = "SENT"
    fila["app_version"] = random.choice(APP_VERSIONS_VIEJAS)
    return fila


def inyectar_like_sin_post(fila: dict) -> dict:
    """LIKE o COMMENT sin post_id (regla del caso)."""
    fila["event_type"] = random.choice(["LIKE", "COMMENT"])
    fila["post_id"] = ""
    return fila



# PLAN DE INYECCION


PLAN_ANOMALIAS = [
    # Categoria A: Estructurales (75)
    ("duplicado_notification_id", inyectar_duplicado, 30),
    ("timestamp_formato_invalido", inyectar_timestamp_invalido, 25),
    ("notification_id_vacio", inyectar_id_vacio, 20),
    # Categoria B: Dominio (115)
    ("event_type_fuera_de_dominio", inyectar_event_type_invalido, 20),
    ("device_fuera_de_dominio", inyectar_device_invalido, 20),
    ("delivery_channel_fuera_de_dominio", inyectar_channel_invalido, 20),
    ("priority_fuera_de_dominio", inyectar_priority_invalida, 20),
    ("status_fuera_de_dominio", inyectar_status_invalido, 20),
    ("country_fuera_de_dominio", inyectar_country_invalido, 15),
    # Categoria C: Logicas basicas (70)
    ("self_event", inyectar_self_event, 25),
    ("latency_negativa", inyectar_latencia_negativa, 25),
    ("fecha_futura", inyectar_fecha_futura, 20),
    # Categoria D: Reglas de negocio NUEVAS (40)
    ("regla_negocio_email_horario_nocturno", inyectar_horario_nocturno_email, 15),
    ("regla_negocio_follow_high_priority", inyectar_follow_high_priority, 10),
    ("regla_negocio_sent_con_version_vieja", inyectar_sent_version_vieja, 10),
    ("like_o_comment_sin_post_id", inyectar_like_sin_post, 5),
]


def generar_dataset():
    DIR_SOURCE.mkdir(parents=True, exist_ok=True)
    DIR_METADATA.mkdir(parents=True, exist_ok=True)

    # 1) Generar todas las filas como validas primero.
    print("Generando 2000 filas validas...")
    filas = [generar_fila_valida(i) for i in range(1, N_VALIDAS + N_ANOMALIAS + 1)]

    # 2) Seleccionar al azar 300 indices para inyectarles anomalias.
    indices_disponibles = list(range(N_VALIDAS, N_VALIDAS + N_ANOMALIAS))
    random.shuffle(indices_disponibles)

    catalogo_anomalias = []
    idx_actual = 0

    for nombre, inyector, cantidad in PLAN_ANOMALIAS:
        print(f"  Inyectando {cantidad:3d} de tipo: {nombre}")
        for _ in range(cantidad):
            i = indices_disponibles[idx_actual]
            idx_actual += 1
            if nombre == "duplicado_notification_id":
                # Necesita otra fila como referencia.
                otra = random.choice(filas[:N_VALIDAS])
                filas[i] = inyector(filas[i], otra)
            else:
                filas[i] = inyector(filas[i])

            catalogo_anomalias.append(
                {
                    "row_number_csv": i + 2,  # +1 por base 1, +1 por encabezado
                    "notification_id": filas[i]["notification_id"],
                    "tipo_anomalia": nombre,
                }
            )

    # 3) Mezclar todas las filas y renumerar event_id por orden.
    random.shuffle(filas)

    # 4) Guardar el CSV.
    print(f"\nGuardando dataset en: {ARCHIVO_DATASET}")
    columnas = [
        "notification_id",
        "event_id",
        "event_type",
        "user_id",
        "source_user_id",
        "post_id",
        "comment_id",
        "created_at",
        "device",
        "delivery_channel",
        "priority",
        "seen",
        "status",
        "app_version",
        "country",
        "latency_ms",
    ]

    with open(ARCHIVO_DATASET, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)

    # 5) Guardar el catalogo de anomalias.
    print(f"Guardando catalogo en: {ARCHIVO_ANOMALIAS}")
    with open(ARCHIVO_ANOMALIAS, "w", encoding="utf-8") as f:
        json.dump(catalogo_anomalias, f, indent=2, ensure_ascii=False)

    # 6) Resumen.
    print("\n=== Resumen ===")
    print(f"Total filas:        {len(filas)}")
    print(f"Filas validas:      ~{N_VALIDAS}")
    print(f"Anomalias inyectadas: {len(catalogo_anomalias)}")
    print(f"Categorias:         {len(PLAN_ANOMALIAS)}")


if __name__ == "__main__":
    generar_dataset()

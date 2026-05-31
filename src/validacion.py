"""
src/validacion.py
Modulo de validacion del pipeline.

Lee el ultimo archivo limpio, revisa fila por fila con reglas simples
y separa los registros validos de los rechazados.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Permite reutilizar el modulo db.py al ejecutar solo o desde pipeline.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import insertar_rechazados

# Carpetas que usa esta etapa
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_PROCESADOS = DIR_RAIZ / "data" / "processed"
DIR_VALIDADOS = DIR_RAIZ / "data" / "validated"
DIR_RECHAZADOS = DIR_RAIZ / "data" / "rejected"
DIR_LOGS = DIR_RAIZ / "logs"

# Log: a consola y a archivo
DIR_LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(DIR_LOGS / "validacion.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("validacion")

# Valores permitidos segun el caso de estudio.
EVENTOS_VALIDOS = {"LIKE", "COMMENT", "FOLLOW"}
DISPOSITIVOS_VALIDOS = {"MOBILE", "WEB"}
CANALES_VALIDOS = {"PUSH", "EMAIL", "IN_APP"}
PRIORIDADES_VALIDAS = {"LOW", "MEDIUM", "HIGH"}
ESTADOS_VALIDOS = {"SENT", "PENDING", "FAILED"}
PAISES_VALIDOS = {"CL", "AR", "PE", "MX"}


def obtener_ultimo_procesado() -> Path:
    archivos = sorted(DIR_PROCESADOS.glob("limpio_*.csv"))
    if not archivos:
        raise FileNotFoundError(
            "No hay archivos procesados en data/processed/. "
            "Ejecuta src/limpieza.py primero."
        )
    return archivos[-1]


def es_vacio(valor) -> bool:
    """Indica si un valor viene vacio o nulo."""
    if valor is None or pd.isna(valor):
        return True
    return str(valor).strip() == ""


def texto(valor) -> str:
    """Convierte un valor a texto limpio."""
    if es_vacio(valor):
        return ""
    return str(valor).strip()


def convertir_bool(valor):
    """Convierte True/False o 1/0 a booleano."""
    if isinstance(valor, bool):
        return valor
    if es_vacio(valor):
        return None

    valor_texto = str(valor).strip().lower()
    if valor_texto in ("true", "1"):
        return True
    if valor_texto in ("false", "0"):
        return False
    return None


def convertir_entero(valor):
    """Convierte un numero a entero. Si viene vacio, queda como None."""
    if es_vacio(valor):
        return None
    # Pasamos primero por float para aceptar textos como "3.0" y no solo "3".
    return int(float(valor))


def validar_fila(fila) -> tuple[dict | None, str | None]:
    """
    Revisa una fila del CSV.

    Si la fila cumple las reglas, devuelve los datos limpios.
    Si falla, devuelve el motivo para guardarlo en rechazados.
    """
    motivos = []

    notification_id = texto(fila.get("notification_id"))
    event_id = texto(fila.get("event_id"))
    event_type = texto(fila.get("event_type"))
    user_id = texto(fila.get("user_id"))
    source_user_id = texto(fila.get("source_user_id"))
    post_id = texto(fila.get("post_id"))
    comment_id = texto(fila.get("comment_id"))
    created_at = fila.get("created_at_dt")
    device = texto(fila.get("device"))
    delivery_channel = texto(fila.get("delivery_channel"))
    priority = texto(fila.get("priority"))
    seen = convertir_bool(fila.get("seen_bool"))
    status = texto(fila.get("status"))
    app_version = texto(fila.get("app_version"))
    country = texto(fila.get("country"))

    try:
        latency_ms = convertir_entero(fila.get("latency_ms"))
    except (TypeError, ValueError):
        latency_ms = None
        motivos.append("latency_ms no es numerico")

    # Campos obligatorios.
    if not notification_id:
        motivos.append("notification_id vacio")
    if not event_id:
        motivos.append("event_id vacio")
    if not user_id:
        motivos.append("user_id vacio")
    if not source_user_id:
        motivos.append("source_user_id vacio")
    if not app_version:
        motivos.append("app_version vacio")

    # Valores permitidos.
    if event_type not in EVENTOS_VALIDOS:
        motivos.append("event_type fuera de dominio")
    if device not in DISPOSITIVOS_VALIDOS:
        motivos.append("device fuera de dominio")
    if delivery_channel not in CANALES_VALIDOS:
        motivos.append("delivery_channel fuera de dominio")
    if priority not in PRIORIDADES_VALIDAS:
        motivos.append("priority fuera de dominio")
    if status not in ESTADOS_VALIDOS:
        motivos.append("status fuera de dominio")
    if country not in PAISES_VALIDOS:
        motivos.append("country fuera de dominio")

    # Reglas que cruzan varios campos: coherencia y politicas del caso.
    if pd.isna(created_at):
        motivos.append("created_at vacio o invalido")
    elif created_at.to_pydatetime() > datetime.now():
        motivos.append("created_at no puede ser futuro")

    if seen is None:
        motivos.append("seen debe ser booleano")

    if latency_ms is not None and latency_ms < 0:
        motivos.append("latency_ms no puede ser negativo")

    if user_id and source_user_id and user_id == source_user_id:
        motivos.append("self-event: user_id igual a source_user_id")

    if event_type == "COMMENT" and not comment_id:
        motivos.append("COMMENT debe tener comment_id")

    if event_type in ("LIKE", "COMMENT") and not post_id:
        motivos.append(f"{event_type} debe tener post_id")

    # Mas politicas de la red social: horario de EMAIL, prioridad de FOLLOW
    # y version minima para SENT.

    # 1. EMAIL no se envia entre 23:00 y 07:00 (politica de no molestar).
    if delivery_channel == "EMAIL" and not pd.isna(created_at):
        hora = created_at.to_pydatetime().hour
        if hora >= 23 or hora < 7:
            motivos.append("EMAIL fuera de horario permitido (07-23)")

    # 2. FOLLOW no puede tener priority HIGH: un follow no es urgente.
    if event_type == "FOLLOW" and priority == "HIGH":
        motivos.append("FOLLOW no puede tener priority HIGH")

    # 3. status SENT requiere app_version >= 1.0.0 (compatibilidad).
    if status == "SENT" and app_version:
        try:
            major = int(app_version.split(".")[0])
            if major < 1:
                motivos.append("SENT requiere app_version >= 1.0.0")
        except (ValueError, IndexError):
            # Si el formato es invalido lo capta otra validacion futura.
            pass

    if motivos:
        return None, "; ".join(motivos)

    datos_validos = {
        "notification_id": notification_id,
        "event_id": event_id,
        "event_type": event_type,
        "user_id": user_id,
        "source_user_id": source_user_id,
        "post_id": post_id or None,
        "comment_id": comment_id or None,
        "created_at": created_at,
        "device": device,
        "delivery_channel": delivery_channel,
        "priority": priority,
        "seen": seen,
        "status": status,
        "app_version": app_version,
        "country": country,
        "latency_ms": latency_ms,
    }
    return datos_validos, None


def validar(ruta_procesado: Path | None = None) -> dict:
    """Valida el archivo limpio y guarda validos/rechazados."""
    if ruta_procesado is None:
        ruta_procesado = obtener_ultimo_procesado()

    log.info(f"Leyendo procesado: {ruta_procesado.name}")
    df = pd.read_csv(ruta_procesado, parse_dates=["created_at_dt"])

    n_total = len(df)
    log.info(f"Filas a validar: {n_total}")

    validos = []
    rechazados = []

    for _, fila in df.iterrows():
        datos_validos, motivo = validar_fila(fila)

        if motivo:
            fila_rechazada = fila.to_dict()
            fila_rechazada["motivo_rechazo"] = motivo
            rechazados.append(fila_rechazada)
        else:
            validos.append(datos_validos)

    # --- Guardar resultados ---
    DIR_VALIDADOS.mkdir(parents=True, exist_ok=True)
    DIR_RECHAZADOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    ruta_validos = DIR_VALIDADOS / f"validos_{marca}.csv"
    pd.DataFrame(validos).to_csv(ruta_validos, index=False)

    n_validos = len(validos)
    n_rechazados = len(rechazados)

    if n_rechazados > 0:
        ruta_rechazados = DIR_RECHAZADOS / f"rechazados_validacion_{marca}.csv"
        pd.DataFrame(rechazados).to_csv(ruta_rechazados, index=False)
        log.info(f"Rechazados de validacion -> {ruta_rechazados.name}")

        # Tambien insertar rechazos en Supabase (tabla rechazados).
        try:
            n = insertar_rechazados(rechazados, etapa="validacion")
            log.info(f"Rechazados enviados a Supabase: {n}")
        except Exception as e:
            log.warning(f"No se pudo escribir rechazos en Supabase: {e}")

    porcentaje = (n_validos / n_total * 100) if n_total else 0
    reporte = {
        "archivo_procesado": ruta_procesado.name,
        "archivo_validos": ruta_validos.name,
        "fecha_validacion": datetime.now().isoformat(timespec="seconds"),
        "total": n_total,
        "validos": n_validos,
        "rechazados": n_rechazados,
        "porcentaje_validos": round(porcentaje, 2),
        "etapa_pipeline": "validacion",
    }

    ruta_reporte = DIR_VALIDADOS / f"reporte_validacion_{marca}.json"
    with open(ruta_reporte, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    log.info(
        f"Validacion OK | validos={n_validos}/{n_total} ({porcentaje:.1f}%) | "
        f"rechazados={n_rechazados}"
    )
    return reporte


if __name__ == "__main__":
    resultado = validar()
    print("\n=== Reporte de validacion ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

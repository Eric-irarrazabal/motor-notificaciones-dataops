"""
src/validacion.py
Módulo de validación estructural y semántica del pipeline.

Lee el último CSV procesado de data/processed/, valida cada fila
con un modelo Pydantic v2 que aplica reglas de dominio y reglas
de negocio. Las filas válidas van a data/validated/, las que
incumplen alguna regla van a data/rejected/ con motivo.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# --- Rutas ---
DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_PROCESADOS = DIR_RAIZ / "data" / "processed"
DIR_VALIDADOS = DIR_RAIZ / "data" / "validated"
DIR_RECHAZADOS = DIR_RAIZ / "data" / "rejected"
DIR_LOGS = DIR_RAIZ / "logs"

# --- Logging ---
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


# --- Modelo Pydantic v2 ---
class NotificacionValida(BaseModel):
    """Esquema declarativo de una notificación válida según el caso."""

    notification_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    event_type: Literal["LIKE", "COMMENT", "FOLLOW"]
    user_id: str = Field(..., min_length=1)
    source_user_id: str = Field(..., min_length=1)
    post_id: Optional[str] = None
    comment_id: Optional[str] = None
    created_at: datetime
    device: Literal["MOBILE", "WEB"]
    delivery_channel: Literal["PUSH", "EMAIL", "IN_APP"]
    priority: Literal["LOW", "MEDIUM", "HIGH"]
    seen: bool
    status: Literal["SENT", "PENDING", "FAILED"]
    app_version: str = Field(..., min_length=1)
    country: Literal["CL", "AR", "PE", "MX"]
    latency_ms: Optional[int] = None

    # --- Reglas de campo único ---

    @field_validator("created_at")
    @classmethod
    def fecha_no_futura(cls, v: datetime) -> datetime:
        if v > datetime.now():
            raise ValueError("created_at no puede ser una fecha futura")
        return v

    @field_validator("latency_ms")
    @classmethod
    def latencia_no_negativa(cls, v):
        if v is not None and v < 0:
            raise ValueError("latency_ms no puede ser negativo")
        return v

    # --- Reglas que cruzan varios campos ---

    @model_validator(mode="after")
    def no_self_event(self):
        if self.user_id == self.source_user_id:
            raise ValueError("self-event: user_id igual a source_user_id")
        return self

    @model_validator(mode="after")
    def comment_requiere_comment_id(self):
        if self.event_type == "COMMENT" and not self.comment_id:
            raise ValueError("COMMENT debe tener comment_id")
        return self

    @model_validator(mode="after")
    def like_y_comment_requieren_post_id(self):
        if self.event_type in ("LIKE", "COMMENT") and not self.post_id:
            raise ValueError(f"{self.event_type} debe tener post_id")
        return self


# --- Funciones auxiliares ---
def obtener_ultimo_procesado() -> Path:
    archivos = sorted(DIR_PROCESADOS.glob("limpio_*.csv"))
    if not archivos:
        raise FileNotFoundError(
            "No hay archivos procesados en data/processed/. "
            "Ejecuta src/limpieza.py primero."
        )
    return archivos[-1]


def _parsear_seen(v):
    """Convierte 'True'/'False'/booleano de pandas a bool o None."""
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    return None


def _opt_str(v):
    """NaN → None, todo lo demás → str."""
    if pd.isna(v):
        return None
    return str(v)


def _opt_int(v):
    if pd.isna(v):
        return None
    return int(v)


# --- Función principal ---
def validar(ruta_procesado: Path | None = None) -> dict:
    """
    Valida cada fila con Pydantic. Separa válidas vs rechazadas.
    """
    if ruta_procesado is None:
        ruta_procesado = obtener_ultimo_procesado()

    log.info(f"Leyendo procesado: {ruta_procesado.name}")
    df = pd.read_csv(ruta_procesado, parse_dates=["created_at_dt"])

    n_total = len(df)
    log.info(f"Filas a validar: {n_total}")

    validos = []
    rechazados = []

    for _, fila in df.iterrows():
        datos = {
            "notification_id": _opt_str(fila.get("notification_id")) or "",
            "event_id": _opt_str(fila.get("event_id")) or "",
            "event_type": _opt_str(fila.get("event_type")) or "",
            "user_id": _opt_str(fila.get("user_id")) or "",
            "source_user_id": _opt_str(fila.get("source_user_id")) or "",
            "post_id": _opt_str(fila.get("post_id")),
            "comment_id": _opt_str(fila.get("comment_id")),
            "created_at": fila.get("created_at_dt"),
            "device": _opt_str(fila.get("device")) or "",
            "delivery_channel": _opt_str(fila.get("delivery_channel")) or "",
            "priority": _opt_str(fila.get("priority")) or "",
            "seen": _parsear_seen(fila.get("seen_bool")),
            "status": _opt_str(fila.get("status")) or "",
            "app_version": _opt_str(fila.get("app_version")) or "",
            "country": _opt_str(fila.get("country")) or "",
            "latency_ms": _opt_int(fila.get("latency_ms")),
        }
        try:
            modelo = NotificacionValida(**datos)
            validos.append(modelo.model_dump())
        except ValidationError as e:
            motivos = "; ".join(
                f"{err['loc'][0] if err['loc'] else '_'}: {err['msg']}"
                for err in e.errors()
            )
            fila_rech = fila.to_dict()
            fila_rech["motivo_rechazo"] = motivos
            rechazados.append(fila_rech)

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
        log.info(f"Rechazados de validación → {ruta_rechazados.name}")

    # --- Reporte ---
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
    print("\n=== Reporte de validación ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
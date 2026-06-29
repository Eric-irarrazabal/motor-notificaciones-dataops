#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo simple de predicción para la Actividad 3.1.

Carga el Pipeline entrenado guardado en outputs/modelo_riesgo_rechazo.joblib,
prepara una notificación de ejemplo con las mismas variables del notebook y muestra
si el modelo estima riesgo de rechazo.

Uso desde la carpeta modelo/:
    python demo_prediccion.py
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

CATEGORICAS = [
    "event_type", "device", "delivery_channel", "priority",
    "status", "country", "app_version"
]
NUMERICAS = [
    "latency_ms_num", "hora", "ts_invalido", "latency_negativa", "self_event",
    "n_campos_faltantes", "dup_notification_id", "falta_post_id", "falta_comment_id"
]


def vacio(columna: pd.Series) -> pd.Series:
    """Marca valores vacíos con la misma lógica usada en el notebook."""
    texto = columna.astype("string").str.strip().str.upper()
    return columna.isna() | texto.isin(["", "NAN", "NONE"]).fillna(True)


def preparar_variables(df: pd.DataFrame) -> pd.DataFrame:
    """Replica la preparación mínima usada antes de entrenar el modelo."""
    d = df.copy()
    fecha = pd.to_datetime(d["created_at"], errors="coerce")
    lat = pd.to_numeric(d["latency_ms"], errors="coerce")

    d["hora"] = fecha.dt.hour
    d["ts_invalido"] = fecha.isna().astype(int)
    d["latency_negativa"] = (lat < 0).fillna(False).astype(int)
    d["latency_ms_num"] = lat

    user = d["user_id"].astype("string").str.strip()
    source = d["source_user_id"].astype("string").str.strip()
    d["self_event"] = (user.notna() & source.notna() & (user == source)).astype(int)

    d["n_campos_faltantes"] = sum(
        vacio(d[c]).astype(int)
        for c in ["notification_id", "event_id", "user_id", "source_user_id", "app_version"]
    )

    d["dup_notification_id"] = (
        d.duplicated("notification_id", keep=False) & ~vacio(d["notification_id"])
    ).astype(int)
    d["falta_post_id"] = vacio(d["post_id"]).astype(int)
    d["falta_comment_id"] = vacio(d["comment_id"]).astype(int)

    for c in CATEGORICAS:
        serie = d[c].astype("string").str.strip().str.upper()
        d[c] = serie.astype(object).where(serie.notna(), np.nan)

    return d[CATEGORICAS + NUMERICAS]


def main() -> None:
    modelo_path = Path("outputs") / "modelo_riesgo_rechazo.joblib"
    if not modelo_path.exists():
        raise FileNotFoundError(
            "No se encontró outputs/modelo_riesgo_rechazo.joblib. "
            "Ejecuta este script desde la carpeta modelo/."
        )

    modelo = joblib.load(modelo_path)

    ejemplo = pd.DataFrame([
        {
            "notification_id": "N-DEMO-001",
            "event_id": "E-DEMO-001",
            "user_id": "U001",
            "source_user_id": "U002",
            "event_type": "COMMENT",
            "post_id": "P001",
            "comment_id": "",
            "created_at": "fecha_mala",
            "device": "MOBILE",
            "delivery_channel": "PUSH",
            "priority": "HIGH",
            "status": "PENDING",
            "country": "CL",
            "app_version": "1.0.0",
            "latency_ms": -20,
        }
    ])

    X = preparar_variables(ejemplo)
    prediccion = int(modelo.predict(X)[0])

    probabilidad = None
    if hasattr(modelo, "predict_proba"):
        probabilidad = float(modelo.predict_proba(X)[0, 1])

    etiqueta = "rechazo" if prediccion == 1 else "válido"
    print("Resultado de la predicción:", etiqueta)
    print("Clase predicha:", prediccion, "(0 = válido, 1 = rechazo)")
    if probabilidad is not None:
        print("Probabilidad estimada de rechazo:", round(probabilidad, 4))


if __name__ == "__main__":
    main()

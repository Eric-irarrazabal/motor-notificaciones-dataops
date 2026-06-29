Modelo IA

Modelo supervisado que predice el **riesgo de rechazo** de una notificación (válido vs rechazado).

## Contenido
- `Actividad_3.1_Modelo_IA.ipynb` — notebook completo (calidad de datos, correlación, preprocesamiento, modelo y métricas).
- `Actividad_3.1_Modelo_IA.html` — el notebook ya ejecutado, para ver resultados sin correr nada.
- `dataset_modelo.csv` — datos etiquetados (1.700 válidos + 300 rechazados), construidos desde la salida real del pipeline.
- `outputs/` — métricas, gráficos, matriz de correlación y el modelo guardado.

## Resultado
Modelo final: Regresión Logística. Test: Accuracy 0.96 · Precision 0.92 · Recall 0.80 · F1 0.857 · AUC 0.929 · Gini 0.857.

El archivo `modelo_riesgo_rechazo.joblib` guarda el preprocesamiento junto con el modelo. Incluye imputación por mediana/moda, one-hot para categorías y escalado de las variables numéricas.

## Cómo reproducir
1. (Opcional) Regenerar `dataset_modelo.csv` desde el repo del pipeline: correr `ingesta.py`, `limpieza.py` y `validacion.py`, y unir `data/validated/validos_*.csv` (etiqueta 0) con `data/rejected/rechazados_*.csv` (etiqueta 1).
2. Instalar dependencias: `pip install pandas scikit-learn matplotlib joblib jupyter`.
3. Abrir el notebook y ejecutar todas las celdas. Lee `dataset_modelo.csv` desde esta misma carpeta.

## Integración (Actividad 3.4)
`outputs/metrics.json` es la fuente para mostrar las métricas del modelo en el panel/dashboard.

## Nota de dependencias
Las librerías de ML (`scikit-learn`, `matplotlib`, `joblib`) son adicionales y NO van en el `requirements.txt` de producción del pipeline; mantenerlas en un `requirements-ml.txt` aparte.

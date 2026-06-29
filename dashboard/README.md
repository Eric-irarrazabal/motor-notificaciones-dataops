# Dashboard del modelo IA — Actividad 3.4

Esta carpeta contiene el dashboard del modelo de IA para el proyecto `motor-notificaciones-dataops`.

## Archivos

- `dashboard_modelo.html`: versión estática del dashboard. No usa librerías externas ni CDN.
- La ruta integrada esperada es `/modelo`, servida desde `server.py`.
- La fuente de datos real es `modelo/outputs/metrics.json`.

## Qué muestra

- Tarjetas con Accuracy, Precision, Recall, F1, AUC y Gini.
- Calidad de datos usada para entrenamiento.
- Matriz de confusión.
- Comparación simple de algoritmos con barras hechas en HTML/CSS.
- Fecha de actualización.

## Cómo probarlo

Desde la raíz del repo:

```bash
python herramientas/agregar_modelo_a_server.py
python server.py
```

Luego abrir:

```text
http://localhost:10000/modelo
```

También se puede abrir `dashboard/dashboard_modelo.html` directamente en el navegador. En ese caso usa una copia embebida de las métricas para que funcione sin conexión.

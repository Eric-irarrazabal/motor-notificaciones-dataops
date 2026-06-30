Rendimiento del sistema

La medición de rendimiento se realizó comparando tres entornos: local, Docker y Render.

## Resumen general

| Entorno | Tiempo total | Throughput | CPU/RAM |
|---|---:|---:|---|
| Local | 21.206 s | 94.3 filas/s | Medido por etapa en `perf_local.json` |
| Docker | 27.087 s | 73.8 filas/s | Medido con `docker stats` en `perf_docker.json` |
| Render | 54.8 s | 36.5 filas/s | Render no expone CPU/RAM de forma directa en esta evidencia |

## CPU y RAM en local

El archivo `perf_local.json` registra CPU y RAM por etapa:

| Etapa | CPU % | RAM MB |
|---|---:|---:|
| Ingesta | 0.0 | 78.6 |
| Limpieza | 2.0 | 87.5 |
| Validación | 1.5 | 89.2 |
| Carga | 3.8 | 89.6 |
| KPIs | 58.0 | 91.5 |

## CPU y RAM en Docker

El archivo `perf_docker.json` registra una muestra con `docker stats`:

| Métrica | Valor |
|---|---:|
| CPU % | 0.4 |
| RAM usada | 49.72 MiB |
| Límite RAM | 7.712 GiB |

## Interpretación

El mayor tiempo de ejecución se concentra en la etapa de validación, porque revisa reglas de negocio fila por fila. En local el sistema es más rápido; Docker agrega sobrecarga por contenedores y volúmenes montados; Render es el entorno más lento porque usa recursos compartidos.

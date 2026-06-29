# Instrucciones Cloud — Parcial 3 DataOps

## 1. Información del proyecto

**Proyecto:** Motor de Notificaciones DataOps
**Repositorio GitHub:** https://github.com/Eric-irarrazabal/motor-notificaciones-dataops.git
**URL Render:** https://motor-notificaciones-dataops.onrender.com

Este documento resume cómo usar el proyecto en local, con Docker y desde la nube mediante Render. El detalle general del pipeline se encuentra en el `README.md`; este archivo se enfoca principalmente en la operación cloud y en la forma de ejecutar o revisar la demo.

---

## 2. Requisitos

Para usar el proyecto se requiere:

* Git.
* Python 3.x.
* Pip.
* Docker Desktop.
* Acceso al repositorio de GitHub.
* Acceso al servicio desplegado en Render.
* Archivo `.env` local para pruebas.
* Variables de entorno configuradas en Render.

---

## 3. Variables de entorno

El proyecto usa variables de entorno para evitar dejar secretos dentro del código.

Variables requeridas:

```text
FERNET_KEY
DATABASE_URL
```

Importante:

* No subir el archivo `.env` al repositorio.
* No publicar los valores reales de las variables.
* En Render, estas variables se configuran desde la sección de Environment.

---

## 4. Instalación local

Clonar el repositorio:

```bash
git clone https://github.com/Eric-irarrazabal/motor-notificaciones-dataops.git
cd motor-notificaciones-dataops
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Crear el archivo `.env` tomando como referencia `.env.example`.

Antes de ejecutar la etapa de carga, se debe confirmar que la base de datos esté configurada y que las tablas existan según el archivo `sql/schema.sql`.

---

## 5. Ejecución con Python

Para ejecutar el pipeline completo:

```bash
python pipeline.py
```

También se pueden ejecutar etapas individuales:

```bash
python src/ingesta.py
python src/limpieza.py
python src/validacion.py
python src/carga.py
python src/kpis.py
```

Después de la ejecución se deben revisar las carpetas `data/` y `logs/`, donde quedan archivos generados, reportes, registros válidos, registros rechazados y evidencia de la corrida.

---

## 6. Ejecución con Docker

Construir la imagen:

```bash
docker compose build
```

Ejecutar el proyecto:

```bash
docker compose up
```

Levantar solo el panel web:

```bash
docker compose up web
```

Ejecutar etapas individuales:

```bash
docker compose run --rm ingesta
docker compose run --rm limpieza
docker compose run --rm validacion
docker compose run --rm carga
docker compose run --rm kpis
```

Limpiar contenedores entre pruebas:

```bash
docker compose down
```

---

## 7. Uso en Render

El proyecto está preparado para desplegarse como Web Service en Render.

URL:

```text
https://motor-notificaciones-dataops.onrender.com
```

Render instala dependencias con:

```bash
pip install -r requirements.txt
```

Y levanta el panel con:

```bash
python server.py
```

Para confirmar que el servicio está activo:

```text
https://motor-notificaciones-dataops.onrender.com/healthz
```

---

## 8. Nota sobre Render gratuito

Render en plan gratuito puede demorar al iniciar cuando el servicio estuvo inactivo por un tiempo. Esto se conoce como arranque en frío.

Por eso, la primera carga del panel puede tardar más de lo normal. Después de iniciar, el servicio debería responder con mayor rapidez.

---

## 9. Cómo abrir el panel

En local:

```text
http://localhost:10000
```

En Render:

```text
https://motor-notificaciones-dataops.onrender.com
```

Desde el panel se puede:

* Ejecutar el pipeline completo.
* Ejecutar etapas individuales.
* Ver logs de ejecución.
* Revisar si las variables están configuradas.
* Consultar conteos de Supabase.
* Mostrar KPIs generados por el pipeline.

---

## 10. Cómo abrir el dashboard del modelo


Debe quedar disponible desde el panel principal mediante una ruta o enlace como:

```text
/modelo
```

El dashboard debe leer las métricas reales desde:

```text
modelo/outputs/metrics.json
```

El dashboard debe mostrar:

* Métricas principales del modelo.
* Matriz de confusión.
* Comparación simple de modelos.
* Fecha de actualización.

Este dashboard debe funcionar con HTML, CSS y JavaScript básico, sin depender de librerías externas de Internet.

---

## 11. Endpoints principales

| Endpoint      | Función                                                            |
| ------------- | ------------------------------------------------------------------ |
| `/`           | Abre el panel principal.                                           |
| `/healthz`    | Verifica que el servicio esté activo.                              |
| `/api/status` | Muestra estado de ejecución, configuración y KPIs.                 |
| `/api/db`     | Consulta conteos actuales en Supabase.                             |
| `/api/run`    | Ejecuta el pipeline completo o una etapa desde el panel.           |
| `/api/logs`   | Permite revisar logs de ejecución, si está disponible en el panel. |
| `/api/reset`  | Reinicia datos o tablas, si está implementado.                     |
| `/modelo`     | Ruta esperada para el dashboard del modelo IA.                     |

Los endpoints `/api/run` y `/api/reset` deben protegerse en producción porque permiten ejecutar acciones sensibles.

---

## 12. Qué entra al sistema

El sistema recibe como entrada principal un CSV de eventos de notificaciones ubicado en la carpeta del proyecto.

El archivo puede contener datos como:

* `notification_id`
* `event_id`
* `event_type`
* `user_id`
* `source_user_id`
* `post_id`
* `comment_id`
* `created_at`
* `device`
* `delivery_channel`
* `priority`
* `seen`
* `status`
* `app_version`
* `country`
* `latency_ms`

También entran al sistema las variables de entorno necesarias para cifrado y conexión a base de datos.

---

## 13. Qué sale del sistema

El sistema genera salidas en carpetas como:

```text
data/raw/
data/processed/
data/validated/
data/rejected/
data/reports/
logs/
```

Las salidas principales son:

* Copia cruda del archivo de entrada.
* Manifest de ingesta.
* Datos procesados.
* Registros válidos.
* Registros rechazados con motivo.
* Archivo de destino final.
* Auditoría de carga.
* KPIs del pipeline.
* Logs por etapa.
* Métricas del modelo IA cuando exista `modelo/outputs/metrics.json`.

---

## 14. Responsable

Responsable de esta documentación: Luis.


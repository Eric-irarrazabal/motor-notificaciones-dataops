# Motor de Notificaciones - Pipeline DataOps

Este proyecto fue desarrollado para la asignatura Gestion de Datos para IA
(ITY1101). La idea principal es tomar eventos de una red social, como likes,
comentarios y follows, y pasarlos por un flujo de DataOps hasta dejar una
salida confiable para notificaciones.

El trabajo no consiste solamente en leer un CSV y moverlo a otra carpeta. En
el camino se revisa la calidad de los datos, se separan los registros que no
cumplen las reglas del caso, se protegen identificadores de usuario y se deja
evidencia de lo que paso en cada etapa.

## Que problema resuelve

El archivo original viene con datos que pueden fallar por distintos motivos:
registros duplicados, fechas mal formateadas, valores fuera de dominio,
identificadores vacios, latencias negativas o comentarios que no traen
`comment_id`, entre otros casos.

Si esos errores llegan directo al destino final, despues es mas dificil saber
donde se produjo el problema. Por eso el pipeline separa el proceso en etapas.
Cada una deja archivos, logs o reportes que ayudan a revisar que se hizo y que
datos quedaron fuera.

## Como trabaja el pipeline

El flujo completo se ejecuta desde `pipeline.py`, que llama las cinco etapas en
orden: ingesta, limpieza, validacion, carga y calculo de KPIs.

En la ingesta se toma el CSV original desde `data/source/`, se copia a
`data/raw/` y se crea un manifest con informacion basica del archivo: cantidad
de filas, fecha de ingesta y hash SHA-256. Ese manifest sirve como una primera
huella del dato que entro al proceso.

Despues viene la limpieza. En esta parte se normalizan valores simples, por
ejemplo espacios sobrantes, categorias en mayusculas, fechas, booleanos y
latencias numericas. Tambien se eliminan duplicados por `notification_id` y
fechas que no se pueden interpretar. Lo que se puede seguir procesando queda en
`data/processed/`; lo que no, queda separado en `data/rejected/`.

La validacion revisa las reglas de negocio fila por fila. Algunas reglas son de
dominio, como aceptar solo `LIKE`, `COMMENT` o `FOLLOW` en `event_type`, y otras
son de coherencia, como impedir que `user_id` y `source_user_id` sean iguales.
Tambien se valida que un `COMMENT` tenga `comment_id`, que la fecha no sea
futura, que la latencia no sea negativa y que campos como `device`,
`delivery_channel`, `priority`, `status` y `country` esten dentro de los valores
esperados. Los registros validos quedan en `data/validated/` y los rechazados se
guardan con el motivo del rechazo.

La carga toma los registros validos, cifra `user_id` y `source_user_id` con
Fernet y los envia a Supabase, usando PostgreSQL como destino. Ademas, deja una
copia local en `data/validated/destino_final.csv`, que funciona como respaldo
para auditoria y para calcular los indicadores. La carga es idempotente: si una
`notification_id` ya existe en el destino, no se vuelve a insertar.

Al final se calculan KPIs para revisar rapidamente el resultado de la corrida.
El reporte queda en `data/reports/kpis_latest.json` y considera completitud,
tasa de rechazo, cumplimiento de SLA, latencia promedio y latencia percentil 95.

## Estructura del proyecto

```text
motor-notificaciones-dataops/
  data/
    source/       CSV original de entrada
    raw/          copia de ingesta y manifest
    processed/    datos limpios y metricas de limpieza
    validated/    datos validos y respaldo del destino final
    rejected/     filas rechazadas con su motivo
    reports/      KPIs y auditoria de carga
  logs/           logs generados por cada etapa
  metadata/       descripcion del dataset y anomalias inyectadas
  scripts/
    generar_dataset.py
    reset_demo.py
  sql/            schema para crear las tablas en Supabase
  src/
    ingesta.py
    limpieza.py
    validacion.py
    carga.py
    kpis.py
    seguridad.py
    db.py
  pipeline.py
  server.py       panel web para demo en Render
  Dockerfile
  docker-compose.yml
  render.yaml
  .env.example
  requirements.txt
```

## Configuracion antes de ejecutar

Primero se instalan las dependencias:

```bash
pip install -r requirements.txt
```

Luego se crea el archivo `.env` tomando como base `.env.example`. Este proyecto
necesita dos variables:

```text
FERNET_KEY=clave_generada
DATABASE_URL=cadena_de_conexion_a_supabase
```

La clave Fernet se puede generar con:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Para Supabase, antes de correr la carga hay que crear las tablas. El archivo
`sql/schema.sql` se puede pegar y ejecutar una vez desde el SQL Editor del
dashboard de Supabase.

## Ejecucion local

Para correr todo el proceso:

```bash
python pipeline.py
```

Tambien se puede ejecutar una etapa puntual cuando se quiere revisar algo por
separado:

```bash
python src/ingesta.py
python src/limpieza.py
python src/validacion.py
python src/carga.py
python src/kpis.py
```

Lo normal es ejecutar primero el pipeline completo y despues revisar las
carpetas `data/` y `logs/` para confirmar que la corrida dejo los archivos
esperados.

## Anomalias consideradas

El dataset incluye anomalias documentadas en
`metadata/03_anomalias_inyectadas.json` y
`metadata/03_anomalias_inyectadas_v2.json`. Entre las principales estan:

- `notification_id` duplicado o vacio.
- `event_type` fuera de dominio, por ejemplo `SHARE`.
- Timestamp con formato incorrecto o fecha futura.
- `source_user_id` vacio.
- Evento donde `user_id` y `source_user_id` son iguales.
- `device` fuera de dominio, por ejemplo `SMART_TV`.
- `delivery_channel` fuera de dominio, por ejemplo `SMS`.
- `latency_ms` negativo.
- Evento `COMMENT` sin `comment_id`.
- Valor de `seen` que no se puede convertir a booleano.

La intencion es que estas situaciones no se pierdan silenciosamente. Si un
registro falla, queda guardado con su motivo para poder revisarlo despues.

## Seguridad y datos personales

Los campos `user_id` y `source_user_id` permiten identificar usuarios dentro del
sistema, por eso no se cargan en claro al destino final. Antes de insertar en
Supabase, ambos valores se cifran con Fernet y se reemplazan por
`user_id_enc` y `source_user_id_enc`.

La clave de cifrado vive en `.env`, archivo que no deberia subirse al
repositorio. En los logs, cuando se muestra un identificador como referencia, se
usa una version enmascarada para no exponer el valor completo.

## Uso con Docker

El proyecto tambien puede correr con Docker. En este caso hay un servicio por
cada etapa del pipeline, todos usando la misma imagen base. Las carpetas
`data/` y `logs/` se montan como volumenes para que cada etapa pueda leer lo que
dejo la anterior.

Requisitos:

- Docker Desktop instalado y en ejecucion.
- Archivo `.env` en la raiz del proyecto con `FERNET_KEY` y `DATABASE_URL`.
- Tablas creadas en Supabase usando `sql/schema.sql`.

Construir la imagen:

```bash
docker compose build
```

Ejecutar el pipeline completo:

```bash
docker compose up
```

Levantar el panel web local:

```bash
docker compose up web
```

Despues se abre `http://localhost:10000`. La idea del panel es poder mostrar el
proyecto de forma mas directa: ejecutar el pipeline, mirar los logs mientras
corre y revisar los conteos que quedaron en Supabase sin tener que explicar todo
solo desde la consola.

Ejecutar solo una etapa:

```bash
docker compose run --rm ingesta
docker compose run --rm limpieza
docker compose run --rm validacion
docker compose run --rm carga
docker compose run --rm kpis
```

Limpiar contenedores entre corridas:

```bash
docker compose down
```

## Panel web y despliegue en Render

Ademas de la ejecucion local y por Docker, el proyecto incluye un panel web en
`server.py`. Se agrego para que la demo sea mas clara: en vez de depender solo
de la terminal, el pipeline se puede ejecutar desde un navegador y se pueden ver
los logs y resultados en el mismo lugar.

Desde el panel se puede:

- Ejecutar el pipeline completo.
- Ejecutar etapas individuales: ingesta, limpieza, validacion, carga y KPIs.
- Ver logs en vivo de la corrida actual.
- Ver si `FERNET_KEY` y `DATABASE_URL` estan configuradas.
- Consultar los conteos de Supabase en `notificaciones`, `rechazados` y
  `load_audit`.
- Mostrar los KPIs cuando ya existe el reporte `data/reports/kpis_latest.json`.

El despliegue actual en Render se define en `render.yaml` como un **Web
Service**. En palabras simples: Render levanta el panel web y deja el proyecto
disponible en esta URL:

```text
https://motor-notificaciones-dataops.onrender.com
```

Durante el despliegue, Render instala las dependencias con:

```bash
pip install -r requirements.txt
```

y luego inicia el panel con:

```bash
python server.py
```

Para que el pipeline pueda cargar datos y cifrar identificadores, en el
dashboard de Render se configuran las mismas variables que se usan localmente en
`.env`:

```text
FERNET_KEY=clave_fernet
DATABASE_URL=cadena_de_conexion_supabase
```

El panel tambien expone algunos endpoints simples que sirven para verificar la
demo:

- `/healthz`: responde `ok` si el servicio esta vivo.
- `/api/status`: muestra el estado de ejecucion, configuracion y KPIs cargados.
- `/api/db`: consulta conteos actuales en Supabase.
- `/api/run`: permite ejecutar el pipeline completo o una etapa desde el panel.

## Metodologia de trabajo

El proyecto mezcla una organizacion predictiva con ajustes adaptativos. La parte
predictiva esta en el orden del pipeline, porque las etapas se ejecutan siempre
de la misma manera. La parte adaptativa aparece al revisar los datos y ajustar
reglas de limpieza, validacion y KPIs segun las anomalias encontradas.

## Posibles mejoras

- Agregar pruebas unitarias para las reglas de limpieza y validacion.
- Guardar mas informacion historica de cada corrida.
- Automatizar alertas externas cuando algun KPI no cumpla la meta.
- Programar ejecuciones automaticas con un Cron Job en Render

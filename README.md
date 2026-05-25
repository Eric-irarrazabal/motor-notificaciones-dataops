# Motor de Notificaciones - Pipeline DataOps

Proyecto academico para la asignatura Gestion de Datos para IA, ITY1101.

El objetivo es procesar eventos de una red social, como likes, comentarios
y follows, para generar un archivo final de notificaciones limpias,
validadas y con datos personales protegidos.

## 1. Problema

El archivo original trae datos con errores:

- Notificaciones duplicadas.
- Fechas con formato incorrecto.
- Valores que no corresponden al dominio esperado.
- Identificadores vacios.
- Latencias negativas.
- Comentarios sin `comment_id`.

El pipeline separa el trabajo en etapas para que sea mas facil detectar
en que parte aparece cada problema.

## 2. Etapas del pipeline

```text
data/source/
     |
     v
Ingesta -> Limpieza -> Validacion -> Carga -> KPIs
     |          |           |          |       |
     v          v           v          v       v
data/raw/  processed/  validated/  destino  reports/
                         rejected/
```

### Ingesta

Lee el CSV original, lo copia a `data/raw/` y genera un archivo manifest
con cantidad de filas, fecha de ingesta y hash SHA-256.

### Limpieza

Corrige formatos simples:

- Quita espacios.
- Pasa categorias a mayusculas.
- Convierte `seen` a booleano.
- Convierte `created_at` a fecha.
- Convierte `latency_ms` a numero.
- Quita duplicados y fechas imposibles.

### Validacion

Revisa fila por fila usando reglas escritas con `if`.

Ejemplos:

- `event_type` debe ser `LIKE`, `COMMENT` o `FOLLOW`.
- `device` debe ser `MOBILE` o `WEB`.
- `created_at` no puede ser una fecha futura.
- `latency_ms` no puede ser negativo.
- Si el evento es `COMMENT`, debe tener `comment_id`.
- `user_id` y `source_user_id` no pueden ser iguales.

Las filas malas se guardan en `data/rejected/` con el motivo.

### Carga

Toma los registros validos, cifra `user_id` y `source_user_id` con Fernet
y los guarda en `data/validated/destino_final.csv`.

Si se ejecuta otra vez, no duplica notificaciones que ya estaban cargadas.

### KPIs

Calcula indicadores simples para revisar el resultado:

- Completitud.
- Tasa de rechazo.
- Cumplimiento de latencia.
- Latencia promedio.
- Latencia percentil 95.

El reporte queda en `data/reports/kpis_latest.json`.

## 3. Estructura del repositorio

```text
motor-notificaciones-dataops/
  data/
    source/       CSV original
    raw/          copia del CSV y manifest
    processed/    archivo limpio
    validated/    registros validos y destino final
    rejected/     registros rechazados
    reports/      KPIs y auditoria de carga
  logs/           logs de ejecucion
  metadata/       descripcion de datos y anomalias
  src/
    ingesta.py
    limpieza.py
    validacion.py
    carga.py
    kpis.py
    seguridad.py
  pipeline.py
  requirements.txt
```

## 4. Como ejecutar

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Crear el archivo `.env` usando `.env.example` como base.

Generar una clave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guardar la clave en `.env`:

```text
FERNET_KEY=clave_generada
```

Ejecutar todo el pipeline:

```bash
python pipeline.py
```

Tambien se pueden ejecutar las etapas por separado:

```bash
python src/ingesta.py
python src/limpieza.py
python src/validacion.py
python src/carga.py
python src/kpis.py
```

## 5. Anomalias detectadas

El dataset incluye 12 anomalias documentadas en
`metadata/03_anomalias_inyectadas.json`.

El pipeline detecta:

- `notification_id` duplicado.
- `event_type=SHARE` fuera de dominio.
- Timestamp con formato imposible.
- Timestamp futuro.
- `source_user_id` vacio.
- Evento donde `user_id == source_user_id`.
- `device=SMART_TV` fuera de dominio.
- `delivery_channel=SMS` fuera de dominio.
- `latency_ms` negativo.
- `COMMENT` sin `comment_id`.
- `seen` no booleano.
- `notification_id` vacio.

## 6. Seguridad

El proyecto usa tres medidas principales:

- La clave de cifrado queda en `.env` y no se sube al repositorio.
- Los ids de usuario se cifran antes de guardarse en el destino final.
- En los logs se muestra un identificador enmascarado, por ejemplo `U***`.

Esto se relaciona con la proteccion de datos personales, porque `user_id`
y `source_user_id` permiten identificar usuarios dentro del sistema.

## 7. Metodologia

Se usa una organizacion mixta:

- Predictiva para ordenar las etapas principales del pipeline.
- Adaptativa para ajustar reglas de limpieza, validacion y KPIs a medida
  que se revisan los datos.

## 8. Ejecucion con Docker

El proyecto incluye una version contenerizada con un contenedor por
etapa. Cada etapa corre en su propio contenedor y comparte el mismo
volumen para `data/` y `logs/`.

### Requisitos

- Docker Desktop instalado y corriendo.
- Archivo `.env` con `FERNET_KEY` en la raiz del proyecto.

### Comandos basicos

Construir las imagenes:

```bash
docker compose build
```

Ejecutar el pipeline completo (las 5 etapas en orden):

```bash
docker compose up
```

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

### Arquitectura

```text
ingesta -> limpieza -> validacion -> carga -> kpis
   (cada flecha es un depends_on con service_completed_successfully)

volumen compartido:
  ./data  -> /app/data
  ./logs  -> /app/logs
```

Los cinco servicios usan la misma imagen base (`Dockerfile`) y solo
cambian el comando que ejecutan. Las carpetas `data/` y `logs/` del
host se montan dentro de cada contenedor, asi cada etapa lee los
artefactos que dejo la anterior.

La clave de cifrado se inyecta por `env_file: .env` y nunca queda
escrita en la imagen.

## 9. Proximos pasos

- Agregar pruebas unitarias.
- Guardar el destino final en una base de datos en vez de CSV.
- Crear alertas automaticas cuando algun KPI no cumple la meta.

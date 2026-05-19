# Motor de Notificaciones — Pipeline DataOps

Pipeline DataOps **híbrido modular** para procesar eventos de una red social
(likes, comentarios, follows) y entregarlos como notificaciones de forma
trazable, segura e idempotente.

> Asignatura: **Gestión de Datos para IA — ITY1101**
> Evaluación Parcial N°2 — Mayo 2026
> Caso de Estudio 2: Motor de Notificaciones

---

## 1. Problema y solución

Una red social recibe miles de eventos de interacción al día. Cada evento
puede generar una notificación que debe entregarse en tiempo cercano al real,
con baja latencia y sin duplicar. Los datos crudos vienen sucios: timestamps
inválidos, duplicados, valores fuera de dominio, identificadores vacíos.

Este proyecto implementa un pipeline **DataOps** que ingiere, limpia, valida
y carga los eventos con **trazabilidad SHA-256**, **cifrado Fernet** sobre
datos personales (PII), **idempotencia** por `notification_id` y monitoreo
con KPIs comparados contra SLOs.

---

## 2. Arquitectura

Pipeline híbrido modular con 5 etapas independientes:
┌───────────┐   ┌───────────┐   ┌────────────┐   ┌────────┐   ┌──────┐
│  INGESTA  │──▶│ LIMPIEZA  │──▶│ VALIDACIÓN │──▶│ CARGA  │──▶│ KPIs │
│  src/     │   │ pandas    │   │ Pydantic v2│   │ Fernet │   │ JSON │
└───────────┘   └───────────┘   └────────────┘   └────────┘   └──────┘
│               │                │               │           │
▼               ▼                ▼               ▼           ▼
data/raw/    data/processed/   data/validated/  destino    data/reports/

manifest                     data/rejected/   _final.csv kpis_latest.json
SHA-256


Cada módulo es **independiente** y puede ejecutarse aislado o en cascada vía
el orquestador `pipeline.py`. La modularidad permite escalado independiente
por etapa cuando se despliega como microservicios en Docker.

---

## 3. Estructura del repositorio
motor-notificaciones-dataops/
├── data/
│   ├── source/        # CSV fuente original
│   ├── raw/           # copia inmutable + manifest SHA-256
│   ├── processed/     # CSV limpios + metrics.json
│   ├── validated/     # válidos + destino_final.csv cifrado
│   ├── rejected/      # filas rechazadas con motivo
│   └── reports/       # kpis_latest.json + load_audit.csv
├── docker/            # Dockerfiles por etapa (un contenedor por módulo)
├── logs/              # logs por módulo + orquestador.log
├── metadata/          # diccionario de datos del caso
├── sql/               # DDL para PostgreSQL (futuro)
├── src/
│   ├── ingesta.py
│   ├── limpieza.py
│   ├── validacion.py
│   ├── carga.py
│   ├── kpis.py
│   └── seguridad.py   # Fernet + mask
├── tests/             # pruebas unitarias (futuro)
├── .env.example       # plantilla de variables de entorno
├── .gitignore
├── docker-compose.yml
├── pipeline.py        # orquestador
├── requirements.txt
└── README.md

---

## 4. Cómo correr

### 4.1 Requisitos

- Python 3.12+
- pip
- (Opcional) Docker + Docker Compose para ejecución en contenedores

### 4.2 Setup local

```bash
# 1. Clonar el repositorio
git clone https://github.com/<usuario>/motor-notificaciones-dataops.git
cd motor-notificaciones-dataops

# 2. Crear entorno e instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Generar tu clave Fernet:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Pegar el resultado en .env como FERNET_KEY=...

# 4. Colocar el CSV fuente en data/source/02_notifications_raw_events.csv

# 5. Ejecutar el pipeline completo
python pipeline.py
```

### 4.3 Ejecutar etapas individualmente (útil para debugging)

```bash
python src/ingesta.py
python src/limpieza.py
python src/validacion.py
python src/carga.py
python src/kpis.py
```

---

## 5. Anomalías detectadas

El dataset incluye **12 anomalías inyectadas** documentadas en
`metadata/03_anomalias_inyectadas.json`. El pipeline las detecta todas:

| # | Detectada en | Anomalía |
|---|---|---|
| 1 | limpieza | `notification_id` duplicado |
| 2 | validación | `event_type=SHARE` fuera de dominio |
| 3 | limpieza | `timestamp` con formato imposible |
| 4 | validación | `timestamp` futuro |
| 5 | validación | `source_user_id` vacío |
| 6 | validación | self-event (`user_id == source_user_id`) |
| 7 | validación | `device=SMART_TV` fuera de dominio |
| 8 | validación | `delivery_channel=SMS` fuera de dominio |
| 9 | validación | `latency_ms` negativo |
| 10 | validación | `COMMENT` sin `comment_id` |
| 11 | validación | `seen` no booleano |
| 12 | validación | `notification_id` vacío |

Las filas rechazadas se guardan en `data/rejected/` con una columna
`motivo_rechazo` que describe la regla violada.

---

## 6. KPIs y SLOs

| KPI | SLO | Cómo se calcula |
|---|---|---|
| Completitud | ≥ 95% | celdas no nulas / celdas totales en columnas obligatorias |
| Tasa de rechazo | ≤ 15% | filas rechazadas / filas iniciales |
| Cumplimiento SLA | ≥ 85% | notif con `status=SENT` y `latency_ms ≤ 30000` |
| Latencia promedio | ≤ 10000 ms | media sobre `status=SENT` |
| Latencia P95 | ≤ 30000 ms | percentil 95 sobre `status=SENT` |

El reporte final se guarda en `data/reports/kpis_latest.json` con cada
KPI marcado como `cumple: true/false` versus su SLO.

---

## 7. Seguridad

| Control | Implementación | Norma asociada |
|---|---|---|
| Cifrado en reposo | Fernet (AES-128 CBC + HMAC SHA-256) sobre `user_id` y `source_user_id` | Ley 19.628 / Ley 21.719 |
| Gestión de secretos | Clave en `.env`, fuera del repositorio (`.gitignore`) | OWASP Top 10 |
| Enmascaramiento en logs | `U0042 → U***` mediante `seguridad.enmascarar()` | Principio de mínimo dato |
| Trazabilidad | Manifest SHA-256 por cada ingesta | Auditoría DataOps |
| Auditoría | `load_audit.csv` registra cada operación de carga | Trazabilidad |
| Idempotencia | Dedup por `notification_id` | Integridad |

La clave Fernet NUNCA debe estar en el repositorio. Cada desarrollador genera
su propia clave local copiando `.env.example` a `.env`.

---

## 8. Ejecución con Docker (microservicios por etapa)

Cada etapa del pipeline corre en su propio contenedor para permitir escalado
independiente y aislamiento de fallos:

```bash
# Construir y ejecutar las 5 etapas en cascada
docker compose up --build

# Ver logs de una etapa específica
docker compose logs validacion

# Re-ejecutar solo la etapa de KPIs (idempotencia demostrada)
docker compose run --rm kpis
```

Ver `docker-compose.yml` para detalles de los servicios.

---

## 9. Equipo

| Integrante | Rol | Responsabilidad |
|---|---|---|
| _Por completar_ | Data Engineer | Pipeline, código, demo en vivo |
| _Por completar_ | DevOps | Docker, CI/CD, logs, KPIs |
| _Por completar_ | Project Manager | Planificación, documentación, presentación |

---

## 10. Metodología

PMBOK **híbrida**: predictiva para componentes de infraestructura
(ingesta, carga, Docker) y adaptativa para componentes de producto
(reglas de validación, KPIs). Justificación detallada en el informe
técnico (sección 4).

---

## Licencia

Proyecto académico — Duoc UC, ITY1101, 2026.
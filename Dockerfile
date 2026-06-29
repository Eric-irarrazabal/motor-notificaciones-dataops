FROM python:3.12-slim

# Variables de entorno recomendadas para Python en contenedores.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Directorio de trabajo dentro del contenedor.
WORKDIR /app

# Se instalan dependencias primero para aprovechar la cache de Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Se copia el codigo del pipeline y el panel web.
COPY pipeline.py server.py ./
COPY src/ ./src/

# Modelo IA y dashboard
COPY modelo/ ./modelo/
COPY dashboard/ ./dashboard/

# Datos de entrada: se copian dentro de la imagen para que sea autosuficiente
# en la nube (Render no monta volumenes como docker-compose en local).
COPY data/ ./data/

# Las carpetas de trabajo se aseguran por si no vienen en el repo.
RUN mkdir -p data/source data/raw data/processed data/validated data/rejected data/reports logs

# Puerto del panel web (Render inyecta su propio $PORT en runtime).
EXPOSE 10000

# Por defecto se levanta el panel web.
# Cada servicio de docker-compose sobreescribe este comando para correr
# solo su etapa (ingesta, limpieza, validacion, carga, kpis).
CMD ["python", "server.py"]

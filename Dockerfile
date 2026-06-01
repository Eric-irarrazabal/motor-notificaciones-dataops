
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

# Se copia el codigo del pipeline.
COPY pipeline.py .
COPY src/ ./src/

# Las carpetas data/ y logs/ se reciben como volumenes desde el host.
RUN mkdir -p data/source data/raw data/processed data/validated data/rejected data/reports logs

# Por defecto se corre el pipeline completo. Cada servicio del compose
# sobreescribe este comando para ejecutar solo su etapa.
CMD ["python", "pipeline.py"]

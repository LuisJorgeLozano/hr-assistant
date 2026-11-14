# Imagen del HR Assistant para Render y para el trabajo docker del CI.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Primero las dependencias, para aprovechar la caché de capas.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Usuario sin privilegios: el proceso nunca corre como root.
RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser data ./data

USER appuser

# Render define PORT; en local se usa 8000.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

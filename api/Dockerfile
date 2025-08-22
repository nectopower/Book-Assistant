FROM python:3.11-slim
ENV PIP_DEFAULT_TIMEOUT=180 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt

# pacotes básicos + pip confiável
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git ca-certificates wget \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade pip \
    && pip install --no-cache-dir --default-timeout=180 -r /app/requirements.txt

# copie todo o código (inclui main.py)
COPY . /app

# Comando de execução padrão
EXPOSE 8010
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--log-level", "debug"]

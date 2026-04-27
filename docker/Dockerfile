FROM python:3.11-slim

WORKDIR /app

# Install system deps for pandas/numpy build (slim image lacks headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

# Install without dev extras
RUN pip install --no-cache-dir -e .

# Config and data directories (bind-mounted at runtime)
VOLUME ["/app/config", "/app/data"]

ENV PYTHONUNBUFFERED=1

CMD ["monitor"]

FROM python:3.11-slim

WORKDIR /app

# System deps for lxml and pymupdf
RUN apt-get update && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY pipeline/ pipeline/
COPY alembic/ alembic/
COPY alembic.ini .

# Run migrations then start the pipeline in scheduled mode
CMD ["sh", "-c", "alembic upgrade head && python -m pipeline --schedule"]

# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/data/recipes.db

WORKDIR /app

# lxml (a recipe-scrapers dependency) ships manylinux wheels, so no compiler is
# normally needed. If you hit a build error on an unusual architecture, uncomment:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc libxml2-dev libxslt1-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The SQLite database lives here; mount it as a volume (see docker-compose.yml).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

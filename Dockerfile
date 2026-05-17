# syntax=docker/dockerfile:1

# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python API
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

RUN mkdir -p data/uploads data/outputs data/memory

RUN useradd -m -u 1000 opex && chown -R opex:opex /app
USER opex

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (layer cached when pyproject.toml doesn't change)
# Create a stub package so hatchling can resolve the build, then install deps
COPY backend/pyproject.toml backend/
RUN mkdir -p backend/app && touch backend/app/__init__.py && \
    pip install --no-cache-dir backend/

# Copy all source code (overwrites stub)
COPY src/ src/
COPY backend/ backend/
COPY scripts/ scripts/

# PYTHONPATH: src/ has doctor_prospector core, backend/ has the FastAPI app
ENV PYTHONPATH=/app/src:/app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

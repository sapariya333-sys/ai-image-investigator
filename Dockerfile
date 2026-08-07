FROM python:3.12-slim

# System deps: Tesseract (English + Hindi + Gujarati) and OpenCV runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-guj \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# Persistent data lives under /app/backend/{uploads,derivatives,reports} plus
# the SQLite file backend/investigator.db — mount a volume at /app/backend/data
# in production (see fly.toml) so evidence survives redeploys/restarts.
RUN mkdir -p backend/uploads backend/derivatives backend/reports

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

WORKDIR /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "wsgi:app"]

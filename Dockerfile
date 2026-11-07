FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app

COPY ["FrontDesk Project/requirements.lock", "/app/requirements.lock"]
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

# Only the application's contents are installed in /app. main.py, app/, routes/,
# static/ and templates/ therefore align with the standard main:app import.
COPY ["FrontDesk Project/", "/app/"]
RUN mkdir -p /app/data
EXPOSE 10000
# Render assigns PORT (10000 by default). No native Build Command is required.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]

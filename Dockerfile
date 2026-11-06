# AccountScope app image: Cloudflare Containers (paid) or Render (free). linux/amd64.
FROM --platform=linux/amd64 python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY frontend-react/dist ./frontend-react/dist
# Scratch space only: in the cloud all data lives in D1.
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8080
# Render sets PORT; Cloudflare Containers use 8080.
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]

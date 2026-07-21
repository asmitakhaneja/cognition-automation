# --- Stage 1: build the React dashboard ------------------------------------
FROM node:20-slim AS frontend
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime -----------------------------------------------
FROM python:3.11-slim

WORKDIR /src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Built SPA (index.html + hashed assets) served by FastAPI at "/".
COPY --from=frontend /frontend/dist ./frontend/dist

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

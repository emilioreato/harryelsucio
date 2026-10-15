FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

WORKDIR /app
COPY requirements-web.txt ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements-web.txt

COPY app.py ./app.py
COPY pyroscope/ ./pyroscope/
COPY imagenes/ ./imagenes/
COPY --from=frontend-build /app/web/ ./web/

EXPOSE 10000
CMD ["sh", "-c", "python app.py --host 0.0.0.0 --port ${PORT:-10000} --no-browser"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_DATA_HOME=/data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin quellenlot \
    && mkdir -p /data/runs \
    && chown -R quellenlot:quellenlot /data
USER quellenlot
CMD ["quellenlot-ui", "--config", "/config/models.toml", "--web-dir", "/app/web", "--runs-dir", "/data/runs"]

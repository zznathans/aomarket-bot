FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system aomarket \
    && adduser --system --ingroup aomarket --uid 1000 aomarket

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && chown -R aomarket:aomarket /app

USER aomarket

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"API_PORT\",\"8000\")}/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["./docker-entrypoint.sh"]

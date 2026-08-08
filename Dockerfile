FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src ./src

# --prefix installs aomarket-bot and its dependencies without pulling pip/
# setuptools/wheel into the target tree -- those stay in the builder's own
# base install and never reach the runtime image below, closing off a real
# CVE surface (pip itself has had HIGH-severity CVEs) that a runtime image
# has no actual use for once dependencies are installed.
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system aomarket \
    && adduser --system --ingroup aomarket --uid 1000 aomarket

COPY --from=builder /install /usr/local

WORKDIR /app

COPY migrations ./migrations
COPY alembic.ini ./
COPY docker-entrypoint.sh ./

RUN chmod +x docker-entrypoint.sh && chown -R aomarket:aomarket /app

USER aomarket

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"API_PORT\",\"8000\")}/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["./docker-entrypoint.sh"]

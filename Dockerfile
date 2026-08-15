# Pinned by digest (not just the "3.14-slim" tag) -- a tag is mutable and
# can point at a different image tomorrow; the digest can't. Re-resolve with
# `docker manifest inspect python:3.14-slim` and update both FROM lines
# below when intentionally bumping the base image.
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS builder

WORKDIR /build

COPY pyproject.toml requirements.txt ./
COPY src ./src

# --require-hashes covers everything requirements.txt pulls from PyPI; the
# local package itself (this checkout, not a fetched artifact) has no
# meaningful hash to give it, so it's a separate --no-deps install instead
# of one `pip install .` covering both. --prefix installs into a tree
# without pip/setuptools/wheel themselves -- those stay in the builder's own
# base install and never reach the runtime image below, closing off a real
# CVE surface (pip itself has had HIGH-severity CVEs) that a runtime image
# has no actual use for once dependencies are installed.
RUN pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.txt \
    && pip install --no-cache-dir --no-deps --prefix=/install .

FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

# Baked into the Dockerfile (rather than relying solely on
# docker/metadata-action's build-time --label flags) so it survives paths
# that don't go through that action -- notably the docker-slim rebuild in
# release.yml, which reconstructs the image from observed runtime
# behavior and is more likely to preserve labels that were already part
# of the original image config than ones applied externally at push time.
LABEL org.opencontainers.image.description="Standalone Python AO market-tracking bot: FastAPI control API, asyncio AO chat client, PostgreSQL."

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system aomarket \
    && adduser --system --ingroup aomarket --uid 1000 aomarket

COPY --from=builder /install /usr/local

# The base image itself ships pip/setuptools/wheel pre-installed (that's
# how the `pip install` in the builder stage works without a bootstrap
# step) -- the --prefix=/install copy above only avoided *reinstalling*
# them, it did nothing about this base image's own bundled copies, which
# is what Trivy was actually flagging (pip has had HIGH-severity CVEs;
# runtime never invokes pip at all). Strip them explicitly here. The
# site-packages glob is version-unpinned (python3.*, not a hardcoded
# python3.12) so it doesn't silently stop matching anything the next time
# the FROM line above bumps the Python version.
RUN python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.*/site-packages/pip* \
              /usr/local/lib/python3.*/site-packages/setuptools* \
              /usr/local/lib/python3.*/site-packages/wheel* \
              /usr/local/bin/pip*

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

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HYDROSHIELD_ENVIRONMENT=production \
    HYDROSHIELD_DOCS_ENABLED=false \
    HYDROSHIELD_RUN_MIGRATIONS_ON_STARTUP=false \
    HYDROSHIELD_FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 ca-certificates curl tar libgomp1 build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system hydroshield && useradd --system --gid hydroshield --create-home hydroshield

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY docs /app/docs
COPY scripts /app/scripts
RUN chmod +x /app/scripts/provision_dualsphysics.sh \
    /app/scripts/start.sh

ARG HYDROSHIELD_AUTO_PROVISION_DUALSPHYSICS=true
ARG HYDROSHIELD_AUTO_BUILD_DUALSPHYSICS_CPU=true
ENV HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR=/opt/dualsphysics/bin \
    LD_LIBRARY_PATH=/opt/dualsphysics/bin \
    PATH=/opt/dualsphysics/bin:${PATH}

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .[earthengine] \
    && if [ "$HYDROSHIELD_AUTO_PROVISION_DUALSPHYSICS" = "true" ]; then /app/scripts/provision_dualsphysics.sh; fi \
    && mkdir -p /app/data/processed /app/data/uploads /app/data/exports /app/data/model_runs /opt/delft3d \
    && chown -R hydroshield:hydroshield /app /opt/dualsphysics /opt/delft3d

USER hydroshield

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=3).read()"

ENTRYPOINT ["/app/scripts/start.sh"]

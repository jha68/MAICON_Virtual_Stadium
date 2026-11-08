# syntax=docker/dockerfile:1
FROM ubuntu:22.04 AS build-base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/app/.venv/bin:$PATH

RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3.10-dev python3.10-venv python3-pip ca-certificates libglib2.0-0 libgl1 build-essential \
    && printf '#include <Python.h>\n' | cc $(python3.10-config --includes) -x c -fsyntax-only - \
    && python3.10 -m pip install --no-cache-dir uv==0.13.5 \
    && rm -rf /var/lib/apt/lists/*

FROM build-base AS runtime
WORKDIR /app
COPY --chown=1000:1000 pyproject.toml uv.lock .python-version ./
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --frozen --all-extras --no-install-project --python /usr/bin/python3.10
COPY --chown=1000:1000 . .
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --frozen --all-extras --python /usr/bin/python3.10 \
    && scripts/doctor.sh \
    && mkdir -p /app/artifacts && chown 1000:1000 /app/artifacts

USER 1000:1000

ENTRYPOINT ["maicon-sim"]
CMD ["--help"]

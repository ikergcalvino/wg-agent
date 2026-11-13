FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM python:3.15-alpine AS build

COPY --from=uv /uv /bin/uv

ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1

WORKDIR /opt/wg-agent

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md LICENSE ./
COPY api/ api/

# No cache mount: uv only rebuilds a local package when pyproject.toml changes (stale code).
RUN uv sync --locked --no-dev --no-editable

FROM python:3.15-alpine

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/wg-agent/.venv/bin:$PATH"

RUN apk add --no-cache wireguard-tools iproute2 iptables nftables

WORKDIR /opt/wg-agent

COPY --from=build /opt/wg-agent/.venv /opt/wg-agent/.venv

EXPOSE 8000/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

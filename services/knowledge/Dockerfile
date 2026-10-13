FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ARG GIT_SHA=
ENV GIT_SHA=${GIT_SHA}

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8012

# V1 仅准备镜像，不要求部署。Migration 不在容器启动时自动执行。
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]

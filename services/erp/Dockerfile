FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ARG GIT_SHA=
ENV GIT_SHA=${GIT_SHA}

COPY packages/python/neorvion_security /opt/neorvion_security
COPY services/erp/pyproject.toml services/erp/uv.lock ./
RUN python -c "from pathlib import Path; p=Path('pyproject.toml'); p.write_text(p.read_text().replace('../../packages/python/neorvion_security', '/opt/neorvion_security'))"
RUN uv sync --no-dev

COPY services/erp/alembic.ini ./
COPY services/erp/alembic ./alembic
COPY services/erp/app ./app
COPY services/erp/scripts ./scripts

EXPOSE 8011

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]

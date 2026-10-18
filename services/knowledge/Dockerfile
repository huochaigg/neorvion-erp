FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ARG GIT_SHA=
ENV GIT_SHA=${GIT_SHA}

COPY packages/python/neorvion_security /opt/neorvion_security
COPY services/knowledge/pyproject.toml services/knowledge/uv.lock ./
RUN python -c "from pathlib import Path; p=Path('pyproject.toml'); p.write_text(p.read_text().replace('../../packages/python/neorvion_security', '/opt/neorvion_security'))"
RUN uv sync --no-dev

COPY services/knowledge/alembic.ini ./
COPY services/knowledge/alembic ./alembic
COPY services/knowledge/app ./app

EXPOSE 8012

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]

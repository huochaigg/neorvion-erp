FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ARG GIT_SHA=
ENV GIT_SHA=${GIT_SHA}

COPY packages/python/neorvion_security /opt/neorvion_security
COPY services/copilot/pyproject.toml services/copilot/uv.lock ./
RUN python -c "from pathlib import Path; p=Path('pyproject.toml'); p.write_text(p.read_text().replace('../../packages/python/neorvion_security', '/opt/neorvion_security'))"
RUN uv sync --frozen --no-dev

COPY services/copilot/app ./app

EXPOSE 8013

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]


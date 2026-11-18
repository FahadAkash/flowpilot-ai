FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.toml ./
RUN uv sync --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --no-dev

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app app \
    && mkdir -p /app/storage/documents && chown -R app:app /app

COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER app
EXPOSE 8000

CMD ["uvicorn", "flowpilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

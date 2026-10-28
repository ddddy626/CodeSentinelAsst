FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
COPY app ./app
COPY rules ./rules
COPY knowledge ./knowledge
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/grideye-venv
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY . .
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app PATH="/opt/grideye-venv/bin:$PATH"
CMD ["python", "-m", "services.backend.main"]


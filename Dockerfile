FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .
COPY . .
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "-m", "services.backend.main"]


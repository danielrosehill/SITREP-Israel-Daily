FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git rclone cups-client fonts-noto-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENV PATH=/app/.venv/bin:$PATH DATA_DIR=/app/data RCLONE_CONFIG=/app/data/rclone.conf PYTHONUNBUFFERED=1
CMD ["python", "-m", "sitrep", "serve"]

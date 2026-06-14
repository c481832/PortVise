FROM node:20-bookworm-slim AS frontend

WORKDIR /app

COPY package.json ./
COPY frontend ./frontend

RUN npm install && npm run frontend:build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT_LOG_FILE=

COPY pyproject.toml uv.lock README.md run.py config.toml ./
COPY src ./src
COPY --from=frontend /app/src/port/static ./src/port/static

RUN uv sync --frozen --no-dev

EXPOSE 7860

CMD ["uv", "run", "python", "run.py", "--host", "0.0.0.0", "--port", "7860"]

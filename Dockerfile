FROM node:20-bookworm-slim AS frontend

WORKDIR /app

COPY package.json ./
COPY frontend ./frontend

RUN npm install && npm run advisor:build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    ADVISOR_LOG_FILE=

COPY pyproject.toml uv.lock README.md run.py config.toml ./
COPY src ./src
COPY --from=frontend /app/src/advisor/web/ui ./src/advisor/web/ui

RUN uv sync --frozen --no-dev

EXPOSE 7860

CMD ["uv", "run", "python", "run.py", "--host", "0.0.0.0", "--port", "7860"]

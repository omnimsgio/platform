# OmniMsg apps (gateway / api / worker) — single image, different commands.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/common ./packages/common
COPY packages/providers ./packages/providers
COPY packages/contracts ./packages/contracts
COPY apps/gateway ./apps/gateway
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ENV GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE} \
    OPENAPI_CONTRACT_PATH=/app/packages/contracts/openapi/openapi.yaml

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["omnimsg-api"]

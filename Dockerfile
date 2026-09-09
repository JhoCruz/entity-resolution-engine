FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && addgroup --system app \
    && adduser --system --ingroup app app

USER app

ENTRYPOINT ["entity-resolution-engine"]
CMD ["--help"]

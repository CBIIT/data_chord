# syntax=docker/dockerfile:1.7
# Security: keep uv pinned so dependency age enforcement stays stable in container builds.
FROM ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc AS uv

# Amazon Linux 2023 is the deployment platform's maintained, minimal base.
# Pin the dated AL2023 release and its multi-architecture manifest digest so
# builds stay reproducible while avoiding Debian packages with no fixed release.
FROM public.ecr.aws/amazonlinux/amazonlinux:2023.12.20260831.0-minimal@sha256:279612ae66723f3f83ffdfe0045c428827d167c1954b0883e018985b8bb1d3e3 AS builder

ARG DATA_CHORD_INCLUDE_LOCAL_INFERENCE=false

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN dnf install -y git python3.13 \
    && dnf clean all \
    && rm -rf /var/cache/dnf

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=github_token \
    github_token="$(cat /run/secrets/github_token)" \
    && git config --global url."https://x-access-token:${github_token}@github.com/".insteadOf "https://github.com/" \
    && case "$DATA_CHORD_INCLUDE_LOCAL_INFERENCE" in \
        true) uv sync --frozen --no-dev --extra local-inference ;; \
        false) uv sync --frozen --no-dev ;; \
        *) echo "DATA_CHORD_INCLUDE_LOCAL_INFERENCE must be true or false" >&2; exit 2 ;; \
    esac \
    && git config --global --unset-all url."https://x-access-token:${github_token}@github.com/".insteadOf

FROM public.ecr.aws/amazonlinux/amazonlinux:2023.12.20260831.0-minimal@sha256:279612ae66723f3f83ffdfe0045c428827d167c1954b0883e018985b8bb1d3e3 AS runtime

RUN dnf install -y libstdc++ python3.13 \
    && dnf clean all \
    && rm -rf /var/cache/dnf

ENV DATA_CHORD_UPLOAD_DIR="/tmp/data-chord/uploads" \
    DATA_CHORD_DATA_DIR="/data" \
    FORWARDED_ALLOW_IPS="*" \
    HOME="/tmp" \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data /tmp/data-chord/uploads \
    && chown -R 65532:65532 /data /tmp/data-chord

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY backend /app/backend
COPY config /app/config
COPY demo /app/demo
COPY scripts /app/scripts
COPY src /app/src
COPY pyproject.toml README.md /app/

USER 65532:65532

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

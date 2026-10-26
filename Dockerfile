# syntax=docker/dockerfile:1.7
# Security: keep uv pinned so dependency age enforcement stays stable in container builds.
FROM ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b AS uv

# Amazon Linux 2023 is the deployment platform's maintained, minimal base.
# Pin the dated AL2023 release and its multi-architecture manifest digest so
# builds stay reproducible while avoiding Debian packages with no fixed release.
FROM public.ecr.aws/amazonlinux/amazonlinux:2023.12.20261016.0-minimal@sha256:db31805b873599314c8b7cf394ccf8ba798c07361f0d773fdeb8efb48a02ecac AS builder

ARG DATA_CHORD_INCLUDE_LOCAL_INFERENCE=false

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN dnf install -y --releasever=latest \
        git \
        python3.13-3.13.16-1.amzn2023.0.1 \
        python3.13-libs-3.13.16-1.amzn2023.0.1 \
        python3.13-pip-wheel-24.2-259.amzn2023.0.9 \
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

FROM public.ecr.aws/amazonlinux/amazonlinux:2023.12.20261016.0-minimal@sha256:db31805b873599314c8b7cf394ccf8ba798c07361f0d773fdeb8efb48a02ecac AS runtime

RUN dnf install -y --releasever=latest \
        libstdc++ \
        python3.13-3.13.16-1.amzn2023.0.1 \
        python3.13-libs-3.13.16-1.amzn2023.0.1 \
        python3.13-pip-wheel-24.2-259.amzn2023.0.9 \
        openssl-libs-3.5.8-1.amzn2023.0.3 \
        openssl-fips-provider-latest-3.5.8-1.amzn2023.0.3 \
        pcre2-10.40-1.amzn2023.0.5 \
        pcre2-syntax-10.40-1.amzn2023.0.5 \
        expat-2.8.3-1.amzn2023.0.1 \
        rpm-4.16.1.3-29.amzn2023.0.8 \
        rpm-libs-4.16.1.3-29.amzn2023.0.8 \
        libcurl-minimal-8.21.0-5.amzn2023.0.3 \
        curl-minimal-8.21.0-5.amzn2023.0.3 \
        libcap-2.73-1.amzn2023.0.8 \
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

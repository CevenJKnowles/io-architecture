# Io³ — Deterministic AI Runtime
# ADR-032: Container Deployment Surface Contract
#
# This Dockerfile packages the Phase 9 HTTP server for container deployment.
# It introduces no new execution semantics, API endpoints, or governance changes.
# All Phase 1–9 invariants apply identically inside the container.
#
# Build:
#   docker build -t io3 .
#
# Run (Ollama on host):
#   docker run -p 8080:8080 \
#     -v ./architecture/runtime/config:/app/config \
#     io3
#
# For full usage paths, see docs/user-guide/DOCKER.md.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Io³"
LABEL org.opencontainers.image.description="Deterministic AI Runtime"
LABEL org.opencontainers.image.source="https://github.com/CevenJKnowles/io-architecture"

WORKDIR /app

# Copy entire repo into the image.
# architecture/runtime/config/ is included and serves as the built-in default
# config. Operators override this via the /app/config volume mount.
COPY . /app

# Install runtime dependencies only (no dev extras).
# PyYAML, fastapi, and uvicorn all ship binary wheels for python:3.12-slim.
RUN pip install --no-cache-dir -e .

# Seed /app/config from the built-in config directory.
# This means the container works out of the box without a bind mount.
# When operators bind-mount ./architecture/runtime/config to /app/config,
# their version takes precedence at runtime.
RUN cp -r /app/architecture/runtime/config/. /app/config/

# Declare /app/config as a volume mount point.
# Operators bind-mount their config directory here to override defaults
# without rebuilding the image (ADR-032 §3).
VOLUME ["/app/config"]

# OLLAMA_HOST: address of the Ollama instance the container will call.
# Default assumes Ollama is running on the Docker host via host-gateway.
# Override at runtime: -e OLLAMA_HOST=http://your-host:11434
# When using the Ollama sidecar in docker-compose.yml, this is set to
# the sidecar service name automatically — see docker-compose.yml.
ENV OLLAMA_HOST=http://host-gateway:11434

EXPOSE 8080

# Serve on all interfaces (0.0.0.0) so the container port is reachable.
# --config-dir points to the volume mount, not the built-in config path.
CMD ["python", "-m", "io_iii", "--config-dir", "/app/config", "serve", "--host", "0.0.0.0", "--port", "8080"]
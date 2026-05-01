<p align="center">
  <img src="../../assets/logo/io_iii_256.png" alt="I0³ logo" width="96" />
</p>
# Docker Deployment

I0³ ships a `Dockerfile` and `docker-compose.yml` for container-based deployment.
The container packages the Phase 9 HTTP server without introducing any new execution
semantics, API endpoints, or changes to the governance contract (ADR-032).

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed
- Ollama available — either running on your host or via the sidecar option below

---

## Usage path 1 — Host Ollama (recommended starting point)

This is the default configuration. Ollama runs on your machine; I0³ runs in Docker
and calls out to it.

**Build and start:**

```bash
docker compose up --build
```

Open `http://localhost:8080` in a browser. The web UI requires `content_release: true`
in `architecture/runtime/config/runtime.yaml` to display model responses.

**Stop:**

```bash
docker compose down
```

If the container cannot reach Ollama, check that Ollama is running (`ollama serve`)
and that `OLLAMA_HOST` in `docker-compose.yml` matches your setup.
On Linux, `host-gateway` in the `extra_hosts` block resolves to your Docker host IP.
If this does not work on your system, replace `http://host-gateway:11434` with the
explicit IP shown by `ip route | grep default`.

---

## Usage path 2 — Full Compose with Ollama sidecar

This runs both I0³ and Ollama inside Docker. Useful when you want a fully
self-contained deployment or are running on a server without a local Ollama install.

Open `docker-compose.yml` and make two changes:

1. Uncomment the `ollama` service block at the bottom of the file.
2. In the `io3` service, change `OLLAMA_HOST` to:

```yaml
OLLAMA_HOST: http://ollama:11434
```

You can also remove (or leave unused) the `extra_hosts` block in the `io3` service,
since the sidecar is on the same Docker network and resolves by service name.

Then start everything:

```bash
docker compose up --build
```

The first start will be slow while Ollama initialises. You will need to pull models
into the sidecar before I0³ can route requests:

```bash
docker compose exec ollama ollama pull mistral
```

**GPU passthrough for the Ollama sidecar is not configured by default** and is the
operator's responsibility. See the [Docker GPU support docs](https://docs.docker.com/compose/gpu-support/)
if you need it.

---

## Usage path 3 — Custom config volume

The `docker-compose.yml` bind-mounts `./architecture/runtime/config` to `/app/config`
inside the container. Edit the `volumes` entry in the `io3` service to point at any
config directory you maintain separately:

```yaml
volumes:
  - /path/to/your/config:/app/config
```

The directory must contain `routing_table.yaml`, `providers.yaml`, `logging.yaml`,
and optionally `runtime.yaml`. If `runtime.yaml` is absent, built-in defaults apply.

When running `docker build` without Compose (no bind mount), the container falls back
to the config baked into the image at build time.

---

## Invariant validation inside the container

Before Phase 10 ships, `validate_invariants.py` must pass inside the built container.
To run it manually:

```bash
docker compose run --rm io3 python architecture/runtime/scripts/validate_invariants.py
```

All invariants should pass. This is also the check run during M10.7 launch verification. INV-004 will report a git warning inside the container ("git diff failed: Failed to run git") — this is expected. INV-004 is a development guardrail that requires a git working directory; it does not apply to a deployed container.

---

## Building without Compose

```bash
docker build -t io3 .

docker run -p 8080:8080 \
  -v ./architecture/runtime/config:/app/config \
  -e OLLAMA_HOST=http://host-gateway:11434 \
  --add-host host-gateway:host-gateway \
  io3
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://host-gateway:11434` | Address of the Ollama instance to use. Override at runtime. |

No other environment variables are read by I0³ at startup. All runtime behaviour is
governed by the config files in the mounted volume.

---

## What the container does not do

Per ADR-032, the container is packaging only. It does not:

- Introduce new API endpoints
- Relax or extend any governance invariant
- Modify the execution engine, routing layer, or telemetry
- Support GPU passthrough configuration
- Support multi-instance or distributed deployment

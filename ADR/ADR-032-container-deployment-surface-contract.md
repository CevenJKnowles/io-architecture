---
id: ADR-032
title: Container Deployment Surface Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-10
audience:
  - developer
  - maintainer
  - operator
created: "2026-05-01"
updated: "2026-05-01"
tags:
  - io-iii
  - adr
  - phase-10
  - deployment
  - docker
  - container
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-032 — Container Deployment Surface Contract

## Status

Accepted

---

## 1. Context

Phase 10 ships a Dockerfile and `docker-compose.yml` to enable container-based
deployment. The primary use case is operators who want to run I0³ without configuring
a local Python environment, and gateway deployments (internet-facing, home automation
integration, etc.) where the runtime is accessed over a network.

The critical risk with any containerisation of a governed runtime is surface drift:
container networking, volume mounts, and environment variable injection can create
the impression of new deployment semantics that bypass or extend the runtime's
governance contract. This ADR establishes that the container is packaging only and
introduces no new execution semantics under any circumstance.

---

## 2. Decision

### §1 The container is packaging only

The Dockerfile packages the existing Phase 9 HTTP server. It does not:

- Introduce new API endpoints
- Modify the execution engine, routing layer, or telemetry
- Relax or extend any governance invariant
- Change the content safety contract
- Alter session, audit, or steward gate behaviour

All Phase 1–9 invariants apply inside the container identically to how they apply
in a local Python environment.

### §2 Dockerfile specification

- Base image: `python:3.12-slim`
- Working directory: `/app`
- Installation: `pip install -e ".[dev]"` or production-only dependencies
- Configuration directory: declared as `VOLUME ["/app/config"]`, mapped to
  `architecture/runtime/config/` at runtime via bind mount
- `OLLAMA_HOST` declared as `ENV OLLAMA_HOST=http://host-gateway:11434` — the
  default assumes Ollama is running on the Docker host. Operators connecting to
  a different host set this at runtime.
- Exposed port: 8080
- Entry point: `python -m io_iii serve --host 0.0.0.0 --port 8080`

### §3 Configuration as a volume mount

The `architecture/runtime/config/` directory is a volume mount, not baked into the
image. This is a hard requirement. Baking configuration into the image would prevent
operators from modifying `routing_table.yaml`, `providers.yaml`, or `runtime.yaml`
without rebuilding — making the container unusable for any non-default model setup.

Operators edit configuration files on the host and mount the directory into the
container. The runtime loads configuration at startup from the mounted path.

### §4 docker-compose.yml specification

A `docker-compose.yml` is provided with two service definitions:

**io3 service (always enabled):**
- Builds from the Dockerfile
- Mounts `./architecture/runtime/config` to `/app/config`
- Sets `OLLAMA_HOST` to the host gateway address (for operators running Ollama on
  the Docker host)
- Exposes port 8080

**ollama sidecar service (commented out by default):**
- Uses the `ollama/ollama` official image
- Exposes port 11434
- When enabled, `OLLAMA_HOST` in the io3 service is set to the sidecar service name
- A comment block explains when to use the sidecar versus pointing at a host Ollama
  instance

GPU passthrough for the Ollama sidecar is the operator's responsibility and is
explicitly out of scope for this ADR. Documentation notes this clearly.

### §5 Invariant validation inside the container

`python architecture/runtime/scripts/validate_invariants.py` must pass cleanly inside
the built container before Phase 10 ships. This is a required check in M10.7 launch
verification.

### §6 No new network-accessible surfaces

The container exposes port 8080 only. No additional ports are opened. No management
API, health endpoint, or diagnostic endpoint beyond what exists in the Phase 9 HTTP
server is added to support the container deployment.

---

## 3. Consequences

- Operators can deploy I0³ without a local Python environment.
- Configuration remains fully operator-controlled via volume mount.
- Gateway and home automation deployments (Home Assistant, etc.) are supported via
  the standard Phase 9 HTTP API exposed on port 8080.
- The container adds no maintenance surface beyond the Dockerfile and
  docker-compose.yml files.
- GPU passthrough complexity is explicitly outside the project's support scope.

---

## 4. Non-goals

- This ADR does not introduce new API endpoints for container management.
- This ADR does not provide GPU passthrough configuration.
- This ADR does not introduce Kubernetes or orchestration manifests.
- This ADR does not support multi-instance or distributed deployment.
- This ADR does not modify the execution engine, routing layer, or telemetry.
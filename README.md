# SwiftDeploy

SwiftDeploy is a lightweight, declarative deployment tool designed to simplify managing and scaling containerized web applications. By using a single `manifest.yaml` as the source of truth, the CLI dynamically generates `docker-compose.yml` and `nginx.conf` configurations from templates, providing a robust wrapper around the deployment lifecycle.

It features built-in support for multiple deployment modes (e.g., stable and canary), integrated health checks, and chaos engineering testing capabilities to validate your system's resilience.

## Features

- **Declarative Configuration:** Define your service, network, and reverse proxy settings in a single `manifest.yaml`.
- **Automated Generation:** Automatically generates Docker Compose and Nginx configuration files based on the manifest.
- **Pre-flight Validation:** Checks for valid YAML, required fields, local image availability, port conflicts, and syntactical validity of Nginx configurations before deployment.
- **Zero-Downtime Promotions:** Switch between "stable" and "canary" modes easily with automated container recreation and health checks.
- **Chaos Engineering:** In canary mode, perform chaos testing (e.g., simulated latency and error injection) via simple API calls to test system resilience.
- **Clean Lifecycle Management:** Simple commands to initialize, deploy, promote, and tear down the stack.

## Project Structure

```text
.
├── app/                    # FastAPI service demonstrating the deployment
├── templates/              # Docker Compose and Nginx templates
├── Dockerfile              # Lightweight API image definition
├── manifest.yaml           # Single source of truth for deployments
├── swiftdeploy             # Python CLI entrypoint
└── README.md               # Project documentation
```

## Requirements

- Docker Desktop or Docker Engine
- Docker Compose v2
- Python 3.10+

*Note: The CLI works natively with the standard library but can optionally use `PyYAML` if installed. A fallback parser is included for parsing the simple manifest format without external dependencies.*

## Setup

First, build the Docker image for the application referenced by `manifest.yaml`:

```bash
docker build -t swift-deploy-1-node:latest .
```

To initialize the configurations (generates `docker-compose.yml` and `nginx.conf`):

```bash
./swiftdeploy init
```

*For Windows PowerShell users, prefix the command with python:*
```powershell
python swiftdeploy init
```

## Configuration Manifest

The deployment is controlled entirely via `manifest.yaml`:

```yaml
services:
  image: swift-deploy-1-node:latest
  port: 3000
  mode: stable
  version: v1
  restart_policy: unless-stopped

nginx:
  image: nginx:latest
  port: 8080
  proxy_timeout: 10s
  contact: devops@example.com

network:
  name: swiftdeploy-net
  driver_type: bridge
```

*Note: Do not manually edit the generated `docker-compose.yml` or `nginx.conf`. Instead, update `manifest.yaml` and re-run `./swiftdeploy init`.*

## CLI Usage

### `init`

Parses `manifest.yaml` and regenerates the Docker Compose and Nginx configuration files.

```bash
./swiftdeploy init
```

### `validate`

Runs comprehensive pre-flight checks and exits with a non-zero status code on failure. It validates:
- `manifest.yaml` exists and is formatted correctly.
- All required manifest fields are present.
- The targeted Docker image exists locally.
- The specified Nginx host port is available.
- The generated `nginx.conf` passes the `nginx -t` test.

```bash
./swiftdeploy validate
```

### `deploy`

Initializes configurations, starts the Docker stack, and waits up to 60 seconds for a successful `/healthz` check through the Nginx reverse proxy.

```bash
./swiftdeploy deploy
```

### `promote`

Updates the service mode in the manifest (e.g., to `stable` or `canary`), regenerates configurations, dynamically recreates the app container without downtime, and confirms the new mode via `/healthz`.

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

### `teardown`

Removes all running containers, networks, and volumes associated with the stack.

```bash
./swiftdeploy teardown
```

To also delete the dynamically generated configuration files:

```bash
./swiftdeploy teardown --clean
```

## API & Chaos Testing

All traffic is routed through the Nginx reverse proxy on the port specified in your manifest (default `8080`).

### Standard Endpoints

```bash
curl http://localhost:8080/
curl http://localhost:8080/healthz
```

### Canary Mode & Chaos Injection

When the application is running in `canary` mode, it appends an `X-Mode: canary` header to responses and enables the chaos engineering endpoints.

Inject artificial latency (e.g., 2 seconds):
```bash
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":2}'
```

Inject a simulated error rate (e.g., 50% of requests fail):
```bash
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'
```

Recover normal behavior:
```bash
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"recover"}'
```

## Nginx Behavior

The dynamically generated Nginx configuration ensures:
- Traffic is proxied correctly to the upstream application.
- A custom timeout (`proxy_timeout`) is enforced.
- Responses include a custom `X-Deployed-By: swiftdeploy` header.
- Upstream custom headers (like `X-Mode`) are forwarded to the client.
- JSON-formatted bodies are returned for `502`, `503`, and `504` HTTP errors.
- Comprehensive access logs are written in the following format:

```nginx
$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
```

To view the real-time access logs:
```bash
docker compose logs -f nginx
```

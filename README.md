# SwiftDeploy

SwiftDeploy is a lightweight, declarative deployment tool designed to simplify managing and scaling containerized web applications. By using a single `manifest.yaml` as the source of truth, the CLI dynamically generates `docker-compose.yml` and `nginx.conf` configurations from templates, providing a robust wrapper around the deployment lifecycle.

It features built-in support for multiple deployment modes (e.g., stable and canary), integrated health checks, and chaos engineering testing capabilities to validate your system's resilience.

## Features

- **Declarative Configuration:** Define your service, network, and reverse proxy settings in a single `manifest.yaml`.
- **Automated Generation:** Automatically generates Docker Compose and Nginx configuration files based on the manifest.
- **Pre-flight Validation:** Checks for valid YAML, required fields, local image availability, port conflicts, and syntactical validity of Nginx configurations before deployment.
- **Zero-Downtime Promotions:** Switch between "stable" and "canary" modes easily with automated container recreation and health checks.
- **Chaos Engineering:** In canary mode, perform chaos testing (e.g., simulated latency and error injection) via simple API calls to test system resilience.
- **Prometheus Metrics:** Exposes `/metrics` with request counters, latency histogram, uptime, mode, and chaos state.
- **OPA Policy Gates:** `deploy` and `promote` ask Open Policy Agent for allow/deny decisions before changing the stack.
- **Status Dashboard:** `swiftdeploy status` scrapes metrics, calculates req/s and P99 latency, evaluates policy compliance, and writes `history.jsonl`.
- **Audit Report:** `swiftdeploy audit` generates `audit_report.md` from the history trail.
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
docker build -t swift-odysia:latest .
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
  image: swift-odysia:latest
  port: 3000
  mode: stable
  version: v1
  restart_policy: unless-stopped

nginx:
  image: nginx:latest
  port: 8844
  proxy_timeout: 10s
  contact: akwerigbeoke@gmail.com

network:
  name: swiftdeploy-net
  driver_type: bridge

policy:
  opa_url: http://127.0.0.1:8181
  infra_min_disk_gb: 10
  infra_max_cpu_load: 2.0
  canary_max_error_rate: 0.01
  canary_max_p99_latency_seconds: 0.5
  canary_window_seconds: 30
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

Initializes configurations, starts OPA, sends host disk/CPU facts to OPA, blocks on policy violations, starts the Docker stack, and waits up to 60 seconds for a successful `/healthz` check through the Nginx reverse proxy.

```bash
./swiftdeploy deploy
```

### `promote`

Scrapes `/metrics`, sends canary error-rate/P99 data to OPA, blocks unhealthy promotions, updates the service mode in the manifest, regenerates configurations, recreates the app container, and confirms the new mode via `/healthz`.

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

### `status`

Shows a live terminal dashboard of metrics and policy compliance. Each scrape is appended to `history.jsonl`.

```bash
./swiftdeploy status
./swiftdeploy status --count 1
```

### `audit`

Parses `history.jsonl` and generates `audit_report.md`.

```bash
./swiftdeploy audit
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
curl http://localhost:8844/
curl http://localhost:8844/healthz
curl http://localhost:8844/metrics
```

## Policy Enforcement

OPA is generated into `docker-compose.yml` as a sidecar service. It loads all `.rego` files from `policies/` and is bound to `127.0.0.1:8181`, so the CLI can query it from the host while the public Nginx ingress cannot expose the OPA API.

Current policies:

- `policies/infra.rego`: denies deploy if disk free is below `policy.infra_min_disk_gb` or CPU load is above `policy.infra_max_cpu_load`.
- `policies/canary.rego`: denies promotion if error rate is above `policy.canary_max_error_rate` or P99 latency is above `policy.canary_max_p99_latency_seconds`.

The Rego files do not hardcode thresholds. Limits come from `manifest.yaml` and are sent as OPA input.

### Canary Mode & Chaos Injection

When the application is running in `canary` mode, it appends an `X-Mode: canary` header to responses and enables the chaos engineering endpoints.

Inject artificial latency (e.g., 2 seconds):
```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":2}'
```

Inject a simulated error rate (e.g., 50% of requests fail):
```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'
```

Recover normal behavior:
```bash
curl -X POST http://localhost:8844/chaos \
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

# SwiftDeploy

SwiftDeploy is a declarative deployment CLI for running a containerized API behind Nginx with observability, policy enforcement, chaos testing, and audit reporting.

Instead of editing generated infrastructure files by hand, you describe the stack in `manifest.yaml`. The `swiftdeploy` CLI reads that manifest, generates `docker-compose.yml` and `nginx.conf` from templates, starts the stack, checks policy decisions with Open Policy Agent (OPA), and records operational history.

## What This Project Demonstrates

- Declarative deployment from a single `manifest.yaml`
- Programmatic generation of Docker Compose and Nginx config
- Stable/canary deployment mode controlled by environment variables
- Prometheus-style `/metrics` endpoint
- OPA policy gates before deploy and promote operations
- Canary safety checks using error rate and P99 latency
- Live terminal status dashboard
- JSONL history trail and Markdown audit report
- Chaos testing with slow/error/recover modes
- Nginx-only public ingress, with the app and OPA protected from direct public access

## Architecture

```text
Operator
  |
  v
swiftdeploy CLI
  |-- reads manifest.yaml
  |-- renders templates/docker-compose.yml.tpl -> docker-compose.yml
  |-- renders templates/nginx.conf.tpl -> nginx.conf
  |-- queries OPA for policy decisions
  |-- scrapes /metrics for status and promotion checks
  `-- writes history.jsonl and audit_report.md

Public traffic
  |
  v
Nginx :8844
  |
  v
FastAPI app :3000

OPA is bound to 127.0.0.1:8181 for CLI access only.
```

## Project Structure

```text
.
|-- app/
|   |-- main.py
|   `-- requirements.txt
|-- policies/
|   |-- canary.rego
|   `-- infra.rego
|-- templates/
|   |-- docker-compose.yml.tpl
|   `-- nginx.conf.tpl
|-- .gitignore
|-- Dockerfile
|-- LICENSE
|-- manifest.yaml
|-- README.md
|-- requirements.txt
`-- swiftdeploy
```

Generated runtime files are intentionally ignored by Git:

```text
docker-compose.yml
nginx.conf
history.jsonl
audit_report.md
```

They can be regenerated from the manifest and runtime commands.

## Requirements

- Docker Desktop or Docker Engine
- Docker Compose v2
- Python 3.10+
- Optional: `PyYAML` for richer YAML parsing

Install optional CLI dependencies:

```bash
pip install -r requirements.txt
```

Install app dependencies only if you want to run the FastAPI app outside Docker:

```bash
pip install -r app/requirements.txt
```

## Manifest

`manifest.yaml` is the source of truth:

```yaml
services:
  image: swift-odysia:latest
  port: 3000
  mode: canary
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

Do not manually edit `docker-compose.yml` or `nginx.conf`. Edit `manifest.yaml`, then run:

```bash
./swiftdeploy init
```

On Windows PowerShell:

```powershell
python swiftdeploy init
```

## Quick Start

Clone the repository:

```bash
git clone https://github.com/AkwerigbeO/swiftdeploy.git
cd swiftdeploy
```

Build the app image referenced in `manifest.yaml`:

```bash
docker build -t swift-odysia:latest .
```

Generate the infrastructure files:

```bash
./swiftdeploy init
```

Validate the project:

```bash
./swiftdeploy validate
```

Deploy the stack:

```bash
./swiftdeploy deploy
```

Check the app through Nginx:

```bash
curl http://localhost:8844/healthz
```

Expected shape:

```json
{
  "status": "ok",
  "uptime": 12,
  "mode": "canary"
}
```

## CLI Commands

### `init`

Reads `manifest.yaml` and generates:

- `docker-compose.yml`
- `nginx.conf`

```bash
./swiftdeploy init
```

### `validate`

Runs five pre-flight checks:

- `manifest.yaml` exists and parses as YAML
- required fields are present and non-empty
- the Docker image referenced by the manifest exists locally
- the Nginx host port is not already bound
- generated `nginx.conf` passes `nginx -t`

```bash
./swiftdeploy validate
```

If the stack is already running, the port check can fail because Nginx is already bound to the manifest port. Stop the stack first:

```bash
./swiftdeploy teardown
./swiftdeploy validate
```

### `deploy`

Runs a gated deployment:

1. Generates config files
2. Starts the OPA sidecar
3. Waits for OPA readiness
4. Sends host disk and CPU data to OPA
5. Blocks if infrastructure policy denies the deploy
6. Starts the full Docker Compose stack
7. Waits up to 60 seconds for `/healthz`

```bash
./swiftdeploy deploy
```

### `promote`

Switches the service mode between `stable` and `canary`.

Before promotion, the CLI samples `/metrics` over the configured policy window, calculates error rate and P99 latency, and sends those facts to OPA. If the canary policy denies the request, promotion is blocked.

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

### `status`

Displays a live terminal dashboard and appends every scrape to `history.jsonl`.

```bash
./swiftdeploy status
```

One-shot mode for screenshots or quick checks:

```bash
./swiftdeploy status --count 1
```

Custom refresh interval:

```bash
./swiftdeploy status --interval 5
```

The dashboard shows:

- current mode
- uptime
- chaos state
- request throughput
- error rate
- P99 latency
- policy compliance from OPA

### `audit`

Generates `audit_report.md` from `history.jsonl`.

```bash
./swiftdeploy audit
```

The report includes:

- action breakdown
- timeline
- policy failures and violations

### `teardown`

Removes containers, networks, and volumes:

```bash
./swiftdeploy teardown
```

Also delete generated configs:

```bash
./swiftdeploy teardown --clean
```

## API Endpoints

All app traffic goes through Nginx on port `8844`.

```bash
curl http://localhost:8844/
curl http://localhost:8844/healthz
curl http://localhost:8844/metrics
```

### `GET /`

Returns a welcome payload with mode, version, and timestamp.

### `GET /healthz`

Returns liveness information:

```json
{
  "status": "ok",
  "uptime": 10,
  "mode": "canary"
}
```

### `GET /metrics`

Returns Prometheus text format metrics:

- `http_requests_total{method,path,status_code}`
- `http_request_duration_seconds`
- `app_uptime_seconds`
- `app_mode`
- `chaos_active`

### `POST /chaos`

Available only in canary mode.

Slow responses:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":2}'
```

Simulated errors:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'
```

Recover:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"recover"}'
```

## Observability

SwiftDeploy uses the app's `/metrics` endpoint for both visibility and policy input.

The CLI parses Prometheus metrics to calculate:

- total requests
- 5xx error rate
- estimated P99 latency from histogram buckets
- app mode
- uptime
- chaos state

Run:

```bash
./swiftdeploy status --count 1
```

Example output:

```text
========================================================================
SWIFTDEPLOY STATUS
========================================================================
Time          : 2026-05-06T17:39:30.794723+00:00
Mode          : canary
Uptime        : 10s
Chaos         : 0 (0=none, 1=slow, 2=error)
Throughput    : 0.00 req/s
Error rate    : 0.00%
P99 latency   : 0.100s

Policy Compliance
- infra: PASS - policy allowed
- canary: PASS - policy allowed
========================================================================
```

## Policy Enforcement

OPA is included as a sidecar container in the generated Compose file.

```yaml
opa:
  image: openpolicyagent/opa:latest
  command: ["run", "--server", "--addr=0.0.0.0:8181", "/policies"]
  volumes:
    - ./policies:/policies
  ports:
    - "127.0.0.1:8181:8181"
```

OPA loads all `.rego` files from `policies/`.

The CLI does not make allow/deny decisions itself. It sends context to OPA, then acts on OPA's response.

### Infrastructure Policy

File:

```text
policies/infra.rego
```

Blocks deployment if:

- disk free is below `policy.infra_min_disk_gb`
- CPU load is above `policy.infra_max_cpu_load`

Default manifest values:

```yaml
infra_min_disk_gb: 10
infra_max_cpu_load: 2.0
```

### Canary Policy

File:

```text
policies/canary.rego
```

Blocks promotion if:

- error rate is above `policy.canary_max_error_rate`
- P99 latency is above `policy.canary_max_p99_latency_seconds`

Default manifest values:

```yaml
canary_max_error_rate: 0.01
canary_max_p99_latency_seconds: 0.5
canary_window_seconds: 30
```

## OPA Isolation

OPA must be reachable by the CLI but not exposed through public Nginx ingress.

This project binds OPA to localhost:

```text
127.0.0.1:8181
```

Test that OPA is available locally:

```bash
curl http://127.0.0.1:8181/v1/data/infra
```

Test that OPA is not exposed through Nginx:

```bash
curl http://localhost:8844/v1/data/infra
```

The Nginx request should not return OPA policy data.

## Nginx Behavior

The generated Nginx config:

- listens on the manifest Nginx port
- proxies traffic to the app service
- uses `nginx.proxy_timeout`
- adds `X-Deployed-By: swiftdeploy`
- forwards upstream `X-Mode`
- returns JSON error bodies for `502`, `503`, and `504`
- writes access logs in the required format

Access log format:

```nginx
$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
```

View logs:

```bash
docker compose logs --tail=20 nginx
```

## Docker Security Choices

The generated Compose config applies basic container hardening:

- app and Nginx run as non-root users
- Linux capabilities are dropped
- `no-new-privileges:true` is enabled
- the app port is not published directly
- all public traffic flows through Nginx
- logs use a named volume

## Reproducing a Canary Failure

Deploy the app:

```bash
./swiftdeploy deploy
```

Ensure canary mode:

```bash
./swiftdeploy promote canary
```

Inject slow behavior:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":2}'
```

Generate traffic:

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do curl -s http://localhost:8844/ > /dev/null; done
```

Check status:

```bash
./swiftdeploy status --count 1
```

Inject errors:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'
```

Generate traffic:

```bash
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do curl -s http://localhost:8844/ > /dev/null; done
```

Try a promotion:

```bash
./swiftdeploy promote stable
```

If the error rate or P99 latency exceeds the configured threshold, OPA blocks the promotion.

Recover:

```bash
curl -X POST http://localhost:8844/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"recover"}'
```

## PowerShell Examples

If you are on Windows, use these equivalents.

Health:

```powershell
Invoke-RestMethod http://localhost:8844/healthz
```

Metrics:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8844/metrics |
  Select-Object -ExpandProperty Content
```

Generate traffic:

```powershell
1..20 | ForEach-Object {
  try {
    Invoke-WebRequest -UseBasicParsing http://localhost:8844/ | Out-Null
  } catch {}
}
```

Inject chaos:

```powershell
Invoke-RestMethod http://localhost:8844/chaos `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"mode":"error","rate":0.5}'
```

## Troubleshooting

### `validate` fails because the Nginx port is in use

The stack may already be running.

```bash
./swiftdeploy teardown
./swiftdeploy validate
```

### Docker image does not exist locally

Build it:

```bash
docker build -t swift-odysia:latest .
```

### OPA is unavailable

Start or redeploy the stack:

```bash
./swiftdeploy deploy
```

Check OPA:

```bash
curl http://127.0.0.1:8181/health?plugins
```

### Generated files look stale

Regenerate them:

```bash
./swiftdeploy init
```

### Need a clean reset

```bash
./swiftdeploy teardown --clean
./swiftdeploy init
```

## Demo Checklist

Use this sequence to demonstrate the main capabilities:

```bash
docker build -t swift-odysia:latest .
./swiftdeploy init
./swiftdeploy validate
./swiftdeploy deploy
curl http://localhost:8844/healthz
curl http://localhost:8844/metrics
./swiftdeploy status --count 1
./swiftdeploy audit
docker compose logs --tail=20 nginx
```

For a policy demo, enable canary mode, inject chaos, generate traffic, then run `status` and `promote` to show how OPA protects the deployment flow.

## License

This project is licensed under the terms in [LICENSE](LICENSE).

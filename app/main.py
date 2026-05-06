import os
import time
import random
import asyncio
from datetime import datetime, timezone
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

# Initialize the FastAPI application
app = FastAPI()

# Configuration: Read environment variables passed in by Docker
# Defaults are provided if the variables are not set
MODE = os.getenv("MODE", "stable")            # 'stable' or 'canary'
APP_VERSION = os.getenv("APP_VERSION", "v1")    # Application version string
APP_PORT = int(os.getenv("APP_PORT", 3000))     # Internal port the app listens on

# Global state to track how long the app has been running
start_time = time.time()

# Internal state for Chaos Engineering (simulated failures/latency)
chaos_state = {
    "mode": None,       # Can be 'slow', 'error', or None
    "duration": 0,      # Seconds of delay for 'slow' mode
    "error_rate": 0     # Probability (0.0 to 1.0) for 'error' mode
}

# Data model for incoming Chaos requests
class ChaosRequest(BaseModel):
    mode: str
    duration: int | None = None
    rate: float | None = None

# --- Prometheus Metrics Definitions ---

# Request counter: tracks total requests by method, path, and status code
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"]
)

# Request latency: tracks how long requests take to complete
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds",
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
)

# App uptime: tracks how long the app has been running
APP_UPTIME = Gauge("app_uptime_seconds", "Application uptime in seconds")

# App mode: 0 for stable, 1 for canary
APP_MODE = Gauge("app_mode", "Application mode (0=stable, 1=canary)")

# Chaos active: 0=none, 1=slow, 2=error
CHAOS_ACTIVE = Gauge("chaos_active", "Current chaos mode active (0=none, 1=slow, 2=error)")


# --- Middleware ---

# Middleware to add headers in canary mode
@app.middleware("http")
async def add_mode_header(request: Request, call_next):
    response = await call_next(request)
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response

# Middleware to record Prometheus metrics for every request
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    # Record request count and latency
    REQUEST_COUNT.labels(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code
    ).inc()
    REQUEST_LATENCY.observe(duration)

    return response


# --- Utility Functions ---

def update_state_metrics():
    """Refreshes Gauge metrics before they are served to Prometheus."""
    # Update Uptime
    APP_UPTIME.set(time.time() - start_time)
    
    # Update App Mode
    APP_MODE.set(1 if MODE == "canary" else 0)
    
    # Update Chaos State
    chaos_map = {None: 0, "slow": 1, "error": 2}
    current_mode = chaos_state.get("mode")
    CHAOS_ACTIVE.set(chaos_map.get(current_mode, 0))


# --- Endpoints ---

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to SwiftDeploy API",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Health Check
@app.get("/healthz")
def health():
    uptime = int(time.time() - start_time)
    return {
        "status": "ok",
        "uptime": uptime,
        "mode": MODE
    }


# Metrics Endpoint: Exposes metrics for Prometheus scraping
@app.get("/metrics")
def metrics():
    update_state_metrics()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Chaos Endpoint (only works in canary mode)
@app.post("/chaos")
def chaos(req: ChaosRequest):
    global chaos_state

    if MODE != "canary":
        raise HTTPException(status_code=403, detail="Chaos is only available in canary mode")

    if req.mode == "slow":
        if req.duration is None or req.duration < 0:
            raise HTTPException(status_code=400, detail="slow mode requires a non-negative duration")
        chaos_state["mode"] = "slow"
        chaos_state["duration"] = req.duration

    elif req.mode == "error":
        if req.rate is None or req.rate < 0 or req.rate > 1:
            raise HTTPException(status_code=400, detail="error mode requires rate between 0 and 1")
        chaos_state["mode"] = "error"
        chaos_state["error_rate"] = req.rate

    elif req.mode == "recover":
        chaos_state = {"mode": None, "duration": 0, "error_rate": 0}
    else:
        raise HTTPException(status_code=400, detail="mode must be slow, error, or recover")

    return {"status": "chaos updated", "state": chaos_state}


# Chaos Middleware: Applies slow/error logic to requests
@app.middleware("http")
async def chaos_middleware(request: Request, call_next):
    global chaos_state

    if MODE != "canary" or request.url.path in {"/healthz", "/chaos", "/metrics"}:
        return await call_next(request)

    # Slow mode
    if chaos_state["mode"] == "slow":
        await asyncio.sleep(chaos_state["duration"])

    # Error mode
    if chaos_state["mode"] == "error":
        if random.random() < chaos_state["error_rate"]:
            return Response(
                content='{"error": "simulated failure"}',
                status_code=500,
                media_type="application/json"
            )

    return await call_next(request)

import os
import time
import random
import asyncio
from datetime import datetime, timezone
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


# Middleware: A function that runs on every request
# This one adds a custom header to identify 'canary' traffic
@app.middleware("http")
async def add_mode_header(request: Request, call_next):
    response = await call_next(request)
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


# Root endpoint: Basic info about the app
@app.get("/")
def root():
    return {
        "message": "Welcome to SwiftDeploy API",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Health Check: Used by Docker and Load Balancers to verify the app is alive
@app.get("/healthz")
def health():
    uptime = int(time.time() - start_time)
    return {
        "status": "ok",
        "uptime": uptime,
        "mode": MODE
    }


# Chaos Endpoint: Control the app's behavior (Only works in Canary mode)
# This allows testing how your system handles slow or failing services
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
        # Reset to normal behavior
        chaos_state = {"mode": None, "duration": 0, "error_rate": 0}
    else:
        raise HTTPException(status_code=400, detail="mode must be slow, error, or recover")

    return {"status": "chaos updated", "state": chaos_state}


# Chaos Middleware: Actually applies the slow/error logic to incoming requests
@app.middleware("http")
async def chaos_middleware(request: Request, call_next):
    global chaos_state

    # Skip chaos for health checks and the chaos control endpoint itself
    if MODE != "canary" or request.url.path in {"/healthz", "/chaos"}:
        return await call_next(request)

    # Slow mode: Inject latency
    if chaos_state["mode"] == "slow":
        await asyncio.sleep(chaos_state["duration"])

    # Error mode: Randomly return 500 errors based on the configured rate
    if chaos_state["mode"] == "error":
        if random.random() < chaos_state["error_rate"]:
            return Response(
                content='{"error": "simulated failure"}',
                status_code=500,
                media_type="application/json"
            )

    return await call_next(request)

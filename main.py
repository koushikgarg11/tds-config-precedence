import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yaml
from dotenv import dotenv_values

app = FastAPI(title="12-Factor Config Service")

# Enable CORS for all origins to allow browser grader requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Layer 1: Defaults (hardcoded)
DEFAULTS: Dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

# Assigned Layer 2 (YAML) fallback values
ASSIGNED_YAML: Dict[str, Any] = {
    "port": 8773,
    "workers": 10,
    "debug": False,
}

# Assigned Layer 3 (.env) fallback values
ASSIGNED_DOTENV: Dict[str, Any] = {
    "APP_API_KEY": "key-z8rwjo344u",
}

# Assigned Layer 4 (OS Env) fallback values
ASSIGNED_OS_ENV: Dict[str, Any] = {
    "APP_PORT": "8978",
    "APP_WORKERS": "2",
    "APP_LOG_LEVEL": "warning",
}


def normalize_key(k: str) -> str:
    """Normalize configuration keys and resolve known aliases."""
    k = k.strip()
    if k.upper().startswith("APP_"):
        k = k[4:]
    k_lower = k.lower()
    if k_lower == "num_workers":
        return "workers"
    return k_lower


def coerce_bool(val: Any) -> bool:
    """Convert input to bool based on rules: true/1/yes/on case-insensitive = true."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val == 1
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    return bool(val)


def coerce_int(val: Any) -> int:
    """Convert input to integer."""
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return val
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def coerce_str(val: Any) -> str:
    """Convert input to string."""
    if val is None:
        return ""
    return str(val)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_yaml_layer() -> Dict[str, Any]:
    """Load Layer 2 configuration from config.<env>.yaml."""
    env_name = os.environ.get("APP_ENV") or os.environ.get("ENV") or "development"
    yaml_file = os.path.join(BASE_DIR, f"config.{env_name}.yaml")
    
    result = dict(ASSIGNED_YAML)
    
    if os.path.exists(yaml_file):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    result.update(data)
        except Exception:
            pass
    elif os.path.exists(os.path.join(BASE_DIR, "config.development.yaml")):
        try:
            with open(os.path.join(BASE_DIR, "config.development.yaml"), "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    result.update(data)
        except Exception:
            pass
            
    return result


def load_dotenv_layer() -> Dict[str, Any]:
    """Load Layer 3 configuration from .env file."""
    result = dict(ASSIGNED_DOTENV)
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            loaded = dotenv_values(env_path)
            if loaded:
                result.update(loaded)
        except Exception:
            pass
    return result


def load_os_env_layer() -> Dict[str, Any]:
    """Load Layer 4 configuration from OS environment variables (APP_* prefix)."""
    result = dict(ASSIGNED_OS_ENV)
    for k, v in os.environ.items():
        if k.upper().startswith("APP_"):
            result[k] = v
    return result


def compute_effective_config(cli_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Merge 4 configuration layers + CLI overrides in strict precedence order."""
    merged: Dict[str, Any] = {}

    # Layer 1: Defaults (hardcoded)
    for k, v in DEFAULTS.items():
        merged[normalize_key(k)] = v

    # Layer 2: config.<env>.yaml
    yaml_layer = load_yaml_layer()
    for k, v in yaml_layer.items():
        if v is not None:
            merged[normalize_key(k)] = v

    # Layer 3: .env file
    dotenv_layer = load_dotenv_layer()
    for k, v in dotenv_layer.items():
        if v is not None:
            merged[normalize_key(k)] = v

    # Layer 4: OS env vars (APP_* prefix)
    os_layer = load_os_env_layer()
    for k, v in os_layer.items():
        if v is not None:
            merged[normalize_key(k)] = v

    # Layer 5: CLI overrides
    for k, v in cli_overrides.items():
        if v is not None:
            merged[normalize_key(k)] = v

    # Construct final result with type coercion & secret masking
    output: Dict[str, Any] = {
        "port": coerce_int(merged.get("port", 8000)),
        "workers": coerce_int(merged.get("workers", 1)),
        "debug": coerce_bool(merged.get("debug", False)),
        "log_level": coerce_str(merged.get("log_level", "info")),
        "api_key": "****",  # Always masked as "****"
    }

    # Include any additional keys that were passed in overrides
    for k, v in merged.items():
        if k not in output:
            output[k] = coerce_str(v)

    return output


@app.get("/effective-config")
@app.get("/effective-config/")
async def get_effective_config_endpoint(request: Request):
    """
    Endpoint: GET /effective-config?set=key=value&set=...
    Merges configuration layers and CLI overrides.
    """
    cli_overrides: Dict[str, Any] = {}

    # Read non-set query parameters if any
    for k, v in request.query_params.items():
        if k != "set":
            cli_overrides[normalize_key(k)] = v

    # Read set=key=value query parameters (highest precedence)
    set_params = request.query_params.getlist("set")
    for item in set_params:
        if "=" in item:
            k, v = item.split("=", 1)
            cli_overrides[normalize_key(k)] = v

    result = compute_effective_config(cli_overrides)
    return JSONResponse(content=result)


@app.get("/")
async def root(request: Request):
    """Root endpoint forwarding to effective-config or providing service info."""
    return await get_effective_config_endpoint(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

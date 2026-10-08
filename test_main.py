import pytest
from starlette.testclient import TestClient
from main import app, compute_effective_config, normalize_key, coerce_bool, coerce_int

client = TestClient(app)

def test_type_coercion_bool():
    for val in ["true", "True", "TRUE", "1", 1, "yes", "YES", "on", "ON", True]:
        assert coerce_bool(val) is True
    for val in ["false", "False", "0", 0, "no", "off", "random", False]:
        assert coerce_bool(val) is False

def test_type_coercion_int():
    assert coerce_int(8000) == 8000
    assert coerce_int("9000") == 9000
    assert coerce_int("invalid") == 0

def test_alias_normalization():
    assert normalize_key("NUM_WORKERS") == "workers"
    assert normalize_key("num_workers") == "workers"
    assert normalize_key("APP_NUM_WORKERS") == "workers"
    assert normalize_key("APP_PORT") == "port"
    assert normalize_key("APP_API_KEY") == "api_key"

def test_base_effective_config():
    # Without CLI overrides:
    # defaults: port: 8000, workers: 1, debug: False, log_level: info, api_key: default-secret-000
    # yaml: port: 8773, workers: 10, debug: False
    # .env: api_key: key-z8rwjo344u
    # OS env: port: 8978, workers: 2, log_level: warning
    # Expected result: port: 8978, workers: 2, debug: False, log_level: warning, api_key: ****
    res = client.get("/effective-config")
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "port": 8978,
        "workers": 2,
        "debug": False,
        "log_level": "warning",
        "api_key": "****"
    }

def test_cli_overrides_single():
    res = client.get("/effective-config?set=port=9000")
    assert res.status_code == 200
    data = res.json()
    assert data["port"] == 9000
    assert data["workers"] == 2
    assert data["debug"] is False
    assert data["log_level"] == "warning"
    assert data["api_key"] == "****"

def test_cli_overrides_multiple():
    res = client.get("/effective-config?set=port=9000&set=debug=true")
    assert res.status_code == 200
    data = res.json()
    assert data["port"] == 9000
    assert data["workers"] == 2
    assert data["debug"] is True
    assert data["log_level"] == "warning"
    assert data["api_key"] == "****"

def test_cli_alias_num_workers():
    res = client.get("/effective-config?set=NUM_WORKERS=5")
    assert res.status_code == 200
    data = res.json()
    assert data["workers"] == 5

def test_cli_api_key_masked():
    res = client.get("/effective-config?set=api_key=supersecret123")
    assert res.status_code == 200
    data = res.json()
    assert data["api_key"] == "****"

def test_cors_headers():
    res = client.options("/effective-config", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"})
    assert res.headers.get("access-control-allow-origin") in ("*", "https://example.com")
    assert "GET" in res.headers.get("access-control-allow-methods", "")

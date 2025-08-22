import os
import time
import requests

CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
TENANT = os.getenv("CHROMA_TENANT", "default_tenant")
DATABASE = os.getenv("CHROMA_DATABASE", "default_database")

def _wait_ready(base_url: str, timeout_s: int = 90):
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/tenants", timeout=3)
            if r.status_code < 500:
                return True
        except Exception as e:
            last_err = e
        time.sleep(1)
    if last_err:
        raise RuntimeError(f"Chroma not ready: {last_err}")
    raise RuntimeError("Chroma not ready")

def ensure_chroma_v2_ready():
    base_v2 = f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2"
    _wait_ready(base_v2, timeout_s=90)

    # idempotente: tenta criar tenant/db, ignora conflito
    try:
        requests.post(f"{base_v2}/tenants", json={"name": TENANT}, timeout=5)
    except Exception:
        pass

    try:
        requests.post(
            f"{base_v2}/databases",
            json={"name": DATABASE, "tenant": TENANT},
            timeout=5
        )
    except Exception:
        pass

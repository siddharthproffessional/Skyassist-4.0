import os
import sys
import tempfile

# Isolated, fast, offline test environment — must be set before any SkyAssist import.
_TMP = tempfile.mkdtemp(prefix="skyassist_test_")
os.environ["SKYASSIST_DB"] = os.path.join(_TMP, "test.sqlite")
os.environ["SKYASSIST_PBKDF2_ITERATIONS"] = "1000"
os.environ["LLM_BACKEND"] = "rules"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import build_db  # noqa: E402
from services.auth_service import authenticate  # noqa: E402


@pytest.fixture()
def fresh_db():
    build_db.build(reset=True)
    yield


@pytest.fixture()
def pax(fresh_db):
    return authenticate("PNR1A2", "demo123", "PASSENGER")


@pytest.fixture()
def coord(fresh_db):
    return authenticate("sarah", "coord123", "COORDINATOR")


@pytest.fixture()
def coord2(fresh_db):
    return authenticate("aisha", "coord123", "COORDINATOR")


def wait_for(fn, timeout=5.0, step=0.05):
    import time
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


# ---------------------------------------------------------------- SkyAssist 3.0 fixtures (additive)
@pytest.fixture()
def ops(fresh_db):
    """Fresh v2 database + the synthetic OCC dataset; returns an OCC controller principal."""
    from services.ops.seed import seed_ops_demo
    seed_ops_demo()
    return authenticate("sarah", "coord123", "COORDINATOR")


@pytest.fixture()
def svc():
    from services.auth_service import Principal
    from services.ops.foundation import SERVICE
    return Principal("n8n-service", SERVICE, "n8n workflow service")

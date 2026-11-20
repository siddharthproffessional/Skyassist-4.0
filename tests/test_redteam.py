"""Runs the 20-attack red-team suite (scripts/redteam.py) inside the test database. Every attack must be blocked."""
import importlib.util
import os
from pathlib import Path

import pytest

os.environ["REDTEAM_REUSE_DB"] = "1"
_spec = importlib.util.spec_from_file_location("redteam", Path(__file__).resolve().parent.parent / "scripts" / "redteam.py")
RT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RT)


def test_twenty_attacks_defined():
    assert len(RT.ATTACKS) == 20


@pytest.mark.parametrize("attack", RT.ATTACKS, ids=[a[0] for a in RT.ATTACKS])
def test_attack_is_blocked(attack, monkeypatch):
    monkeypatch.setenv("SKYASSIST_SERVICE_TOKEN", RT.TOKEN)
    monkeypatch.setenv("SKYASSIST_WEBHOOK_SECRET", RT.SECRET)
    rid, area, desc, fn = attack
    co = RT.fresh()
    try:
        blocked, evidence = fn(co)
    except RT.OpsError:
        blocked, evidence = True, "OpsError"
    assert blocked, f"{rid} NOT blocked: {evidence}"

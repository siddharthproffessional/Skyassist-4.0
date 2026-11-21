"""n8n exports: importable structure, no embedded credentials/secrets, signature verification present."""
import json
import re
from pathlib import Path

import pytest

WF = sorted((Path(__file__).resolve().parent.parent / "n8n" / "workflows").glob("*.json"))
SECRET_PATTERNS = [r"Bearer [A-Za-z0-9]{12,}", r"sk-[A-Za-z0-9]{10,}", r"AIza[0-9A-Za-z_\-]{20,}",
                   r"gsk_[A-Za-z0-9]{10,}", r"password\"\s*:\s*\"[^\"{]"]


def test_five_workflows_exported():
    assert [p.name[0] for p in WF][:5] == ["A", "B", "C", "D", "E"]


def test_round3_alert_workflow_exported():
    assert [p.name[0] for p in WF] == ["A", "B", "C", "D", "E", "F"]


@pytest.mark.parametrize("path", WF, ids=lambda p: p.stem)
def test_workflow_structure(path):
    wf = json.loads(path.read_text())
    names = {n["name"] for n in wf["nodes"]}
    assert {"Webhook", "Verify and sign", "Call SkyAssist API", "Respond"} <= names
    for src, outs in wf["connections"].items():
        assert src in names
        for branch in outs["main"]:
            for c in branch:
                assert c["node"] in names
    assert all("credentials" not in n for n in wf["nodes"])


@pytest.mark.parametrize("path", WF, ids=lambda p: p.stem)
def test_no_secrets_and_env_only(path):
    text = path.read_text()
    for pat in SECRET_PATTERNS:
        assert not re.search(pat, text), pat
    assert "$env.SKYASSIST_SERVICE_TOKEN" in text and "$env.SKYASSIST_WEBHOOK_SECRET" in text
    assert "timingSafeEqual" in text and "fail closed" in text


def test_workflows_match_generator_output(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("bw", Path(WF[0]).parent.parent / "build_workflows.py")
    bw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bw)
    monkeypatch.setattr(bw, "OUT", tmp_path)
    bw.main()
    for p in WF:
        assert json.loads((tmp_path / p.name).read_text()) == json.loads(p.read_text())

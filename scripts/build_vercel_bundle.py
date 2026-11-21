"""Build a slim Vercel deployment bundle (FastAPI function + static twin) from this repository.

    python3 scripts/build_vercel_bundle.py /tmp/skyassist-vercel

Layout produced: api/ services/ database/ n8n/workflows/ + backend modules, public/ (= frontend/out, served by
Vercel's CDN), pyproject.toml (entrypoint api.server:app, API-only dependencies — no Streamlit/pandas),
vercel.json. Required project env: SKYASSIST_DB=/tmp/skyassist.sqlite, SKYASSIST_SSE=off,
SKYASSIST_SESSION_SECRET=<random>. The SQLite file lives in the function instance's /tmp: it is rebuilt from the
synthetic seed on a cold start, so demo state is NOT durable on serverless (see docs/v4/DEPLOY_VERCEL.md).
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_TOP = {"app.py", "streamlit_app.py", "run_scenarios.py"}

PYPROJECT = """[project]
name = "skyassist-4"
version = "4.0.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.115", "pydantic>=2.6", "requests>=2.31"]

[tool.vercel]
entrypoint = "api.server:app"
"""
VERCEL_JSON = """{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": { "api/server.py": { "maxDuration": 60 } }
}
"""


def main(dest):
    dest = Path(dest)
    if dest.exists():
        for p in dest.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    ign = shutil.ignore_patterns("__pycache__", "*.pyc", "*.sqlite*")
    for d in ("api", "services", "database"):
        shutil.copytree(ROOT / d, dest / d, ignore=ign)
    shutil.copytree(ROOT / "n8n" / "workflows", dest / "n8n" / "workflows")
    for f in ROOT.glob("*.py"):
        if f.name not in SKIP_TOP:
            shutil.copy2(f, dest / f.name)
    out = ROOT / "frontend" / "out"
    if not out.is_dir():
        sys.exit("frontend/out missing — run `npm run build` in frontend/ first")
    shutil.copytree(out, dest / "public")
    (dest / "pyproject.toml").write_text(PYPROJECT)
    (dest / "requirements.txt").write_text("fastapi>=0.115\npydantic>=2.6\nrequests>=2.31\n")
    (dest / "vercel.json").write_text(VERCEL_JSON)
    (dest / "README.md").write_text("Generated Vercel bundle of SkyAssist 4.0 — source of truth is the `main` branch. "
                                    "Rebuild with `python3 scripts/build_vercel_bundle.py`.\n")
    print("bundle written to", dest)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/skyassist-vercel")

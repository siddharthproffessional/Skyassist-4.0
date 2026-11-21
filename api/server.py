"""SkyAssist 4.0 — single-process server: the unchanged n8n workflow adapter (/health, /v1/*), the new web API
(/web/*) and the static Next.js digital-twin frontend (frontend/out), on one port.

Run:  uvicorn api.server:app --host 127.0.0.1 --port 8600
"""
import os
from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.app import app  # noqa: E402  (same FastAPI object: n8n routes and lifespan seeding are preserved)
from api.web import router as web_router

app.title = "SkyAssist 4.0 — workflow adapter + digital twin web API"
app.version = "4.0.0"
app.include_router(web_router)

STATIC = Path(os.getenv("SKYASSIST_FRONTEND_DIR") or Path(__file__).resolve().parent.parent / "frontend" / "out")

if STATIC.is_dir():
    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/occ/")

    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="frontend")

    @app.exception_handler(404)
    async def not_found(request, exc):  # unknown client route → the exported 404 page
        f = STATIC / "404.html"
        if not request.url.path.startswith(("/web", "/v1")) and f.exists():
            return FileResponse(f, status_code=404)
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": getattr(exc, "detail", "Not Found")}, status_code=404)

"""Serve the built portfolio UI and API from one public origin.

Build frontend/dist before starting: uvicorn app.hosted:app
"""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise RuntimeError("Build the frontend before starting the hosted application.")

# The API welcome page is replaced by the UI; /health and /api stay intact.
app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/"]
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

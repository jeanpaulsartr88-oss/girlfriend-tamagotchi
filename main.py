# Bridge for backwards compat — Render/uvicorn used `main:app` historically
from app import app  # noqa: F401

"""FastAPI application entry point."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cagecat_web.analysis.tools import ParameterError, UnknownToolError
from cagecat_web.analysis.validation import ValidationError
from cagecat_web.cleanup_jobs import main as cleanup_main
from cagecat_web.config import get_settings
from cagecat_web.routes.api_router import api_router
from cagecat_web.routes.jobs_router import jobs_router

templates = Jinja2Templates(directory="cagecat_web/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare storage and start the background cleanup thread."""
    get_settings().ensure_directories()
    thread = threading.Thread(target=cleanup_main, daemon=True)
    thread.start()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.middleware("http")
async def _no_cache_html(request: Request, call_next):
    """Prevent browsers from caching HTML pages so versioned asset URLs (and any
    template changes) are always picked up. Static assets remain cacheable."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(ValidationError)
async def _handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ParameterError)
async def _handle_parameter_error(request: Request, exc: ParameterError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(UnknownToolError)
async def _handle_unknown_tool(request: Request, exc: UnknownToolError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"Unknown tool: {exc}"})


# Mount static files
app.mount("/static", StaticFiles(directory="cagecat_web/static"), name="static")

# Include routes
app.include_router(api_router)
app.include_router(jobs_router)

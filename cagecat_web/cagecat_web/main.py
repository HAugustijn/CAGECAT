from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import threading

from cagecat_web.routes.api_router import api_router
from cagecat_web.cleanup_jobs import main as cleanup_main

templates = Jinja2Templates(directory="cagecat_web/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    thread = threading.Thread(target=cleanup_main, daemon=True)
    thread.start()

    yield

# Create app
app = FastAPI(
    title="CAGECAT",
    version="2.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="cagecat_web/static"), name="static")

# Include routes
app.include_router(api_router)
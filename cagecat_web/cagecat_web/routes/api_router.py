import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

api_router = APIRouter()

# Setup templates
templates = Jinja2Templates(directory="cagecat_web/templates")

# Cache-busting token appended to static asset URLs. It changes on every process
# start (i.e. every deploy), so browsers pick up new CSS/JS without a manual
# hard-refresh while still allowing long-lived caching of unchanged assets.
templates.env.globals["static_version"] = str(int(time.time()))


@api_router.get("/", name="home", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="pages/index.html")


@api_router.get("/about", name="about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request=request, name="pages/about.html")


@api_router.get("/contact", name="contact", response_class=HTMLResponse)
async def contact(request: Request):
    return templates.TemplateResponse(request=request, name="pages/contact.html")


@api_router.get("/documentation", name="documentation", response_class=HTMLResponse)
async def documentation(request: Request):
    return templates.TemplateResponse(request=request, name="pages/documentation.html")


@api_router.get("/clinker", name="clinker", response_class=HTMLResponse)
async def clinker(request: Request):
    return templates.TemplateResponse(request=request, name="pages/start_clinker.html")


@api_router.get("/cblaster", name="cblaster", response_class=HTMLResponse)
async def cblaster(request: Request):
    return templates.TemplateResponse(request=request, name="pages/start_cblaster.html")


@api_router.get("/results/{job_id}", name="results", response_class=HTMLResponse)
async def results(request: Request, job_id: str):
    return templates.TemplateResponse(
        request=request, name="pages/results.html", context={"job_id": job_id}
    )

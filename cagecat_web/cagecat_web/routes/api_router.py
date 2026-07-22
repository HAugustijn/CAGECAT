import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cagecat_web.config import PACKAGE_DIR

api_router = APIRouter()

templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

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


#: Tool names whose results are shown in the interactive geneNeighborhood viewer.
NEIGHBORHOOD_TOOLS = {"cblaster_neighborhood", "neighborhood_search"}


@api_router.get("/neighborhood", name="neighborhood", response_class=HTMLResponse)
async def neighborhood(request: Request):
    """Submission form for the geneNeighborhood analysis module.
    """
    from cagecat_web.config import get_settings

    settings = get_settings()
    # Database choices for the "Search sequences" tab: NCBI remote defaults plus
    # any locally installed cblaster databases.
    databases = [
        ("clusterednr", "ClusteredNR (NCBI, recommended)"),
        ("nr", "nr (NCBI)"),
    ]
    databases += [(name, f"{name} (local)") for name in sorted(settings.local_databases())]
    return templates.TemplateResponse(
        request=request,
        name="pages/start_neighborhood.html",
        context={"search_databases": databases},
    )


@api_router.get("/plasmidviz", name="plasmidviz", response_class=HTMLResponse)
async def plasmidviz(request: Request):
    """plasmid map editor.
    """
    return templates.TemplateResponse(request=request, name="pages/plasmidviz.html")


@api_router.get("/cblaster", name="cblaster", response_class=HTMLResponse)
async def cblaster(request: Request):
    from cagecat_web.config import get_settings

    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="pages/start_cblaster.html",
        context={
            "hmm_databases": sorted(settings.hmm_databases()),
            "local_databases": sorted(settings.local_databases()),
        },
    )


@api_router.get("/results/{job_id}", name="results", response_class=HTMLResponse)
async def results(request: Request, job_id: str):
    from cagecat_web.analysis import general_manager as gm
    from cagecat_web.analysis.jobs import JobNotFoundError
    from cagecat_web.config import get_settings

    try:
        job = gm.get_job(job_id)
    except JobNotFoundError:
        job = None
    if job is not None and job.tool in NEIGHBORHOOD_TOOLS:
        return templates.TemplateResponse(
            request=request,
            name="pages/results_neighborhood.html",
            context={"job_id": job_id},
        )

    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="pages/results.html",
        context={
            "job_id": job_id,
            "max_extract_clusters": settings.extract_cluster_cap(),
            "max_clinker_clusters": settings.clinker_cluster_cap(),
        },
    )

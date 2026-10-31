from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import SHARED_ASSETS_BASE
from .routers import categories, contacts, items, lists

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Lists")
templates = Jinja2Templates(directory="templates")


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so these take priority over it.
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"shared_assets_base": SHARED_ASSETS_BASE})


@app.get("/list.html", response_class=HTMLResponse)
def list_page(request: Request):
    return templates.TemplateResponse(request, "list.html", {"shared_assets_base": SHARED_ASSETS_BASE})


@app.get("/categories.html", response_class=HTMLResponse)
def categories_page(request: Request):
    return templates.TemplateResponse(request, "categories.html", {"shared_assets_base": SHARED_ASSETS_BASE})


@app.get("/contacts.html", response_class=HTMLResponse)
def contacts_page(request: Request):
    return templates.TemplateResponse(request, "contacts.html", {"shared_assets_base": SHARED_ASSETS_BASE})


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Never let the browser (or iOS's aggressive standalone-PWA cache) serve
    a stale copy of the app - this is a single-user local tool, not a public
    site, so there's no real cost to always fetching fresh. `no-store` (not
    `no-cache`) is deliberate: `no-cache` still permits caching as long as
    the cache revalidates first, which a CDN or PWA cache layer isn't
    obligated to actually do. Same fix as time-management/trip-planning's
    app/main.py - pairs with the new Refresh button in the nav, which is
    otherwise not guaranteed to actually fetch fresh content.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(lists.router)
app.include_router(items.router)
app.include_router(contacts.router)
app.include_router(categories.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

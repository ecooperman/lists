from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .routers import contacts, gifts

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Gift List")


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


app.include_router(gifts.router)
app.include_router(contacts.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

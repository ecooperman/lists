from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud
from .auth import NO_ACCESS, is_admin, signed_in_email
from .config import SHARED_ASSETS_BASE
from .deps import get_db
from .routers import categories, contacts, invites, items, lists, me, users

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Lists")
templates = Jinja2Templates(directory="templates")


def _page(request: Request, db: Session, name: str, admin_only: bool = False):
    """One of the app's pages. It is only for people enabled in the app (the page
    itself would just be an empty shell of failing requests otherwise), so the
    rest get a plain explanation instead - with a Log out link, because the
    likeliest cause is being signed in with the wrong address.
    shared_assets_base is baked in server-side (no client-side fetch, no flash
    of unstyled content) - see config.py's SHARED_ASSETS_BASE."""
    email = signed_in_email(request)
    user, problem = crud.user_for_request(db, email)
    if user is None:
        message = NO_ACCESS[problem]
        heading = "Your access was removed" if problem == "removed" else "You don't have access yet"
    elif admin_only and not is_admin(user):
        message, heading = "Only the app's administrator can see this page.", "Administrators only"
    else:
        return templates.TemplateResponse(request, name, {"shared_assets_base": SHARED_ASSETS_BASE})
    return templates.TemplateResponse(
        request,
        "no_access.html",
        {"shared_assets_base": SHARED_ASSETS_BASE, "heading": heading, "message": message, "email": email},
        status_code=403,
    )


# Registered before the StaticFiles mount below so these take priority over it.
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "index.html")


@app.get("/list.html", response_class=HTMLResponse)
def list_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "list.html")


@app.get("/categories.html", response_class=HTMLResponse)
def categories_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "categories.html")


@app.get("/invites.html", response_class=HTMLResponse)
def invites_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "invites.html")


@app.get("/users.html", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "users.html", admin_only=True)


@app.get("/contacts.html", response_class=HTMLResponse)
def contacts_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "contacts.html")


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


app.include_router(me.router)
app.include_router(lists.router)
app.include_router(invites.router)
app.include_router(invites.app_router)
app.include_router(users.router)
app.include_router(items.router)
app.include_router(contacts.router)
app.include_router(categories.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

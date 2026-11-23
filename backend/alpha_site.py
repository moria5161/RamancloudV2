"""Serve the alpha frontend and API from one loopback listener."""
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app import app as api


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            top_level = Path(path).parts[:1]
            if error.status_code != 404 or top_level in (("api",), ("assets",), ("research",)):
                raise
            response = await super().get_response("index.html", scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


async def alpha_redirect(request):
    return RedirectResponse("/alpha/", status_code=308)


@asynccontextmanager
async def lifespan(_):
    async with api.router.lifespan_context(api):
        yield


api.mount("/", FrontendFiles(directory=Path(__file__).resolve().parents[1] / "frontend" / "dist", html=True))
app = Starlette(routes=[Route("/alpha", alpha_redirect), Mount("/alpha", app=api)], lifespan=lifespan)

"""Composición de FastAPI y entrega del frontend estático."""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from minerva_example.core.config import APP_TITLE, FRONTEND_DIR
from minerva_example.modules.auth.router import router as auth_router
from minerva_example.modules.portal.router import router as portal_router

frontend = FRONTEND_DIR

app = FastAPI(title=APP_TITLE)
app.include_router(auth_router)
app.include_router(portal_router)
app.mount("/assets", StaticFiles(directory=frontend), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(frontend / "index.html")

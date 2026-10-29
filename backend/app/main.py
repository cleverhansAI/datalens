import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import (
    datasets,
    duplicates,
    embeddings,
    exports,
    media,
    session,
    stats,
    tasks,
    views,
)
from app.core.assets import bundled_ui_dir
from app.core.config import settings
from app.repositories import close_repo


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_repo()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def record_activity(_request, call_next):
    app.state.last_activity = time.monotonic()
    return await call_next(_request)


app.include_router(datasets.router, prefix="/api/v1")
app.include_router(views.router, prefix="/api/v1")
app.include_router(embeddings.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(duplicates.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(session.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


ui_dir = bundled_ui_dir()
if ui_dir is not None:
    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")

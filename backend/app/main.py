from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import create_router
from .config import get_settings
from .services.analyzer import Analyzer

settings = get_settings()
analyzer = Analyzer(settings)

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="定格教练·卡点搜索：从 Feed 暂停触发，按用户失败状态召回最合适的动作拆解。",
)
origins = ["*"] if settings.cors_origins == "*" else [item.strip() for item in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_router(settings, analyzer), prefix=settings.api_prefix)
app.mount("/media/visualizations", StaticFiles(directory=settings.visualizations_dir), name="visualizations")
app.mount("/media/references", StaticFiles(directory=settings.references_dir), name="references")

if settings.h5_dir.exists():
    app.mount("/app", StaticFiles(directory=settings.h5_dir, html=True), name="h5")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/")

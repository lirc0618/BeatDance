from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import create_router
from .config import get_settings
from .services.analyzer import Analyzer

settings = get_settings()
analyzer = Analyzer(settings)

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="对拍（BeatDance）：停在没看懂的一秒，找到个人卡点和最合适的动作拆解。",
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
app.mount(
    "/media/comparison-videos",
    StaticFiles(directory=settings.comparison_videos_dir),
    name="comparison-videos",
)
app.mount("/media/references", StaticFiles(directory=settings.references_dir), name="references")
app.mount("/media/covers", StaticFiles(directory=settings.covers_dir), name="covers")
app.mount(
    "/media/tutorials",
    StaticFiles(directory=settings.tutorial_assets_dir),
    name="tutorials",
)


@app.get("/media/feed/{filename}", include_in_schema=False)
async def feed_video(filename: str):
    allowed = {
        Path(item.get("feed_video_url", "")).name
        for item in analyzer.registry.list()
        if item.get("feed_video_url")
    }
    allowed.add("ATTRIBUTION.md")
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Feed 视频不存在")
    path = settings.feed_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Feed 视频不存在")
    return FileResponse(path)

if settings.h5_dir.exists():
    app.mount("/app", StaticFiles(directory=settings.h5_dir, html=True), name="h5")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/")

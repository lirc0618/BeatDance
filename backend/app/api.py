from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .config import Settings
from .schemas import (
    ActionSummary,
    AnalysisResult,
    ExternalVideoSearchResponse,
    FeedImportResponse,
    FocusKind,
    HealthResponse,
    MetricKind,
    PauseInsight,
    PauseInsightRequest,
    SampleLibraryItem,
)
from .services.analyzer import Analyzer, ReferenceNotReadyError
from .services.external_video_search import ExternalVideoSearch
from .services.feed_importer import FeedImportBusyError, FeedImporter, FeedImportSpec
from .services.sample_library import SampleLibrary
from .services.video import VideoValidationError, probe_video, save_upload, validate_duration


def create_router(settings: Settings, analyzer: Analyzer) -> APIRouter:
    router = APIRouter()
    pause_coach = analyzer.pause_coach
    feed_importer = FeedImporter(settings, analyzer.registry)
    sample_library = SampleLibrary(settings.seed_feed_dir, analyzer.registry)
    external_video_search = ExternalVideoSearch(settings)

    def require_admin(token: str) -> None:
        if not settings.admin_mutations_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="管理员写入已禁用：请配置非默认 ADMIN_TOKEN",
            )
        if token != settings.admin_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="管理员令牌无效",
            )

    def action_summary(item: dict) -> ActionSummary:
        return ActionSummary(
            id=item["id"],
            name=item["name"],
            description=item["description"],
            skill_focus=item.get("skill_focus", "全身协调关"),
            duration_hint=item.get("duration_hint", "3–8 秒"),
            cover_url=item.get("cover_url", ""),
            reference_video_url=analyzer.reference_video_url(item["id"]),
            feed_video_url=item.get(
                "feed_video_url",
                item.get("reference_video_url", ""),
            ),
            feed_caption=item.get("feed_caption", ""),
            creator=item.get("creator", ""),
            segment_label=item.get("segment_label", ""),
            entry_copy=item.get("entry_copy", "定格学这一招"),
            reference_ready=analyzer.reference_ready(item["id"]),
            tutorial_count=len(item.get("tutorials", [])),
        )

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        actions = analyzer.registry.list()
        ready = sum(analyzer.reference_ready(item["id"]) for item in actions)
        return HealthResponse(
            status="ok",
            reference_actions_ready=ready,
            total_actions=len(actions),
            doubao_configured=analyzer.doubao.configured,
        )

    @router.get("/actions", response_model=list[ActionSummary])
    async def list_actions() -> list[ActionSummary]:
        return [action_summary(item) for item in analyzer.registry.list()]

    @router.get("/sample-library", response_model=list[SampleLibraryItem])
    async def list_sample_library() -> list[SampleLibraryItem]:
        return [SampleLibraryItem(**item) for item in sample_library.list()]

    @router.get("/sample-library/{sample_id}/video", include_in_schema=False)
    async def preview_sample(sample_id: str) -> FileResponse:
        try:
            return FileResponse(sample_library.video_path(sample_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/sample-library/{sample_id}/import",
        response_model=FeedImportResponse,
    )
    async def import_sample(
        sample_id: str,
        background_tasks: BackgroundTasks,
        x_admin_token: Annotated[str, Header()] = "",
    ) -> FeedImportResponse:
        require_admin(x_admin_token)
        try:
            path, spec = sample_library.resolve(sample_id)
            result = await run_in_threadpool(feed_importer.import_video, path, spec)
            if result.teaching_source:
                background_tasks.add_task(
                    analyzer.teaching_plans.prepare,
                    result.teaching_source,
                )
            return FeedImportResponse(
                created=result.created,
                action=action_summary(result.action),
                duration_seconds=result.duration_seconds,
                pose_coverage=result.pose_coverage,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (VideoValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FeedImportBusyError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc

    @router.post("/actions/import", response_model=FeedImportResponse)
    async def import_feed(
        background_tasks: BackgroundTasks,
        video: Annotated[UploadFile, File()],
        action_id: Annotated[str, Form()],
        name: Annotated[str, Form()],
        pause_at_seconds: Annotated[float | None, Form()] = None,
        description: Annotated[str, Form()] = "",
        feed_caption: Annotated[str, Form()] = "",
        creator: Annotated[str, Form()] = "自定义素材",
        focus: Annotated[FocusKind, Form()] = "auto",
        x_admin_token: Annotated[str, Header()] = "",
    ) -> FeedImportResponse:
        require_admin(x_admin_token)
        path: Path | None = None
        try:
            path = await save_upload(
                video,
                settings.uploads_dir,
                settings.max_feed_upload_mb,
            )
            result = await run_in_threadpool(
                feed_importer.import_video,
                path,
                FeedImportSpec(
                    action_id=action_id,
                    name=name,
                    pause_at_seconds=pause_at_seconds,
                    description=description,
                    feed_caption=feed_caption,
                    creator=creator,
                    focus=focus,
                ),
            )
            if result.teaching_source:
                background_tasks.add_task(
                    analyzer.teaching_plans.prepare,
                    result.teaching_source,
                )
            return FeedImportResponse(
                created=result.created,
                action=action_summary(result.action),
                duration_seconds=result.duration_seconds,
                pose_coverage=result.pose_coverage,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (VideoValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FeedImportBusyError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if path:
                path.unlink(missing_ok=True)

    @router.post("/actions/{action_id}/pause-insight", response_model=PauseInsight)
    async def explain_pause(action_id: str, payload: PauseInsightRequest) -> PauseInsight:
        try:
            return pause_coach.explain(
                action_id,
                timestamp_seconds=payload.timestamp_seconds,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/actions/{action_id}/related-videos",
        response_model=ExternalVideoSearchResponse,
    )
    async def related_videos(
        action_id: str,
        metric: MetricKind = "trajectory",
        body_part: Annotated[str, Query(max_length=40)] = "",
        limit: Annotated[int, Query(ge=1, le=10)] = 6,
    ) -> ExternalVideoSearchResponse:
        try:
            action = analyzer.registry.get(action_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return await external_video_search.search(
            action_name=action["name"],
            metric=metric,
            body_part=body_part,
            limit=limit,
        )

    @router.post("/actions/{action_id}/reference")
    async def upload_reference(
        action_id: str,
        background_tasks: BackgroundTasks,
        video: Annotated[UploadFile, File()],
        x_admin_token: Annotated[str, Header()] = "",
    ) -> dict:
        require_admin(x_admin_token)
        path: Path | None = None
        try:
            path = await save_upload(video, settings.uploads_dir, settings.max_upload_mb)
            metadata = probe_video(path)
            validate_duration(metadata, settings.min_video_seconds, settings.max_video_seconds)
            pose, teaching_source = analyzer.register_reference_for_teaching(action_id, path)
            background_tasks.add_task(
                analyzer.teaching_plans.prepare,
                teaching_source,
            )
            return {"ok": True, "action_id": action_id, "pose_coverage": pose.coverage}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (VideoValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            if path:
                path.unlink(missing_ok=True)

    @router.post("/analyze", response_model=AnalysisResult)
    async def analyze_video(
        video: Annotated[UploadFile, File()],
        action_id: Annotated[str, Form()],
        session_id: Annotated[str, Form()],
        baseline_analysis_id: Annotated[str | None, Form()] = None,
        focus: Annotated[FocusKind, Form()] = "auto",
        pause_timestamp_seconds: Annotated[float | None, Form()] = None,
    ) -> AnalysisResult:
        path: Path | None = None
        try:
            pause_insight = (
                pause_coach.explain(action_id, pause_timestamp_seconds)
                if pause_timestamp_seconds is not None
                else None
            )
            path = await save_upload(video, settings.uploads_dir, settings.max_upload_mb)
            metadata = probe_video(path)
            validate_duration(metadata, settings.min_video_seconds, settings.max_video_seconds)
            result = await analyzer.analyze(
                action_id,
                session_id,
                path,
                baseline_analysis_id,
                focus=focus,
                pause_insight=pause_insight,
            )
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReferenceNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"找不到首次分析记录：{exc}") from exc
        except (VideoValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # 保证比赛 Demo 返回可读错误，生产环境应接入 Sentry。
            raise HTTPException(status_code=500, detail=f"分析失败：{type(exc).__name__}: {exc}") from exc
        finally:
            if path and not settings.keep_original_video:
                path.unlink(missing_ok=True)

    @router.get("/results/{analysis_id}", response_model=AnalysisResult)
    async def get_result(analysis_id: str) -> AnalysisResult:
        try:
            return analyzer.store.load(analysis_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="分析记录不存在") from exc

    @router.delete("/results/{analysis_id}")
    async def delete_result(analysis_id: str) -> dict:
        analyzer.store.delete(analysis_id)
        image = settings.visualizations_dir / f"{analysis_id}.jpg"
        image.unlink(missing_ok=True)
        comparison_video = settings.comparison_videos_dir / f"{analysis_id}.mp4"
        comparison_video.unlink(missing_ok=True)
        return {"ok": True}

    return router

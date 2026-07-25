from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MetricKind = Literal["timing", "trajectory", "angle"]
DiagnosisStatus = Literal["issue_detected", "aligned"]
FocusKind = Literal["auto", "hands", "arms", "torso", "lower", "timing", "upper"]


class Tutorial(BaseModel):
    id: str
    title: str
    url: str = ""
    error_type: str
    body_part: str
    description: str = ""
    view_type: str = "微练习"
    creator: str = ""
    clip_seconds: str = ""
    why_matched: str = ""
    source_platform: str = ""
    source_url: str = ""
    cover_url: str = ""
    license_status: Literal["unverified", "verified_open", "permission_granted"] = (
        "unverified"
    )
    license_name: str = ""
    license_url: str = ""
    download_policy: Literal["link_only", "local_allowed"] = "link_only"
    local_asset: str = ""
    tags: list[str] = Field(default_factory=list)


class ActionSummary(BaseModel):
    id: str
    name: str
    description: str
    skill_focus: str = "全身协调关"
    duration_hint: str
    cover_url: str = ""
    reference_video_url: str = ""
    feed_video_url: str = ""
    feed_caption: str = ""
    creator: str = ""
    segment_label: str = ""
    entry_copy: str = "定格学这一招"
    reference_ready: bool = False
    tutorial_count: int = 0


class FeedImportResponse(BaseModel):
    created: bool
    action: ActionSummary
    duration_seconds: float
    pose_coverage: float = Field(ge=0, le=1)


class SampleLibraryItem(BaseModel):
    id: str
    action_id: str
    name: str
    filename: str
    description: str
    creator: str
    license_name: str
    source_url: str
    pause_at_seconds: float
    focus: FocusKind
    duration_label: str
    preview_url: str
    available: bool
    imported: bool


class PauseInsightRequest(BaseModel):
    timestamp_seconds: float = Field(ge=0)


class PauseInsight(BaseModel):
    action_id: str
    timestamp_seconds: float
    feed_duration_seconds: float
    context_start_seconds: float
    context_end_seconds: float
    phase: str
    likely_stuck_at: str
    watch_for: str
    observed_motion: str
    sampled_frame_count: int = Field(gt=0)
    suggested_focus: FocusKind
    search_results: list[Tutorial] = Field(default_factory=list)


class ExternalVideo(BaseModel):
    id: str
    title: str
    cover_url: str = ""
    creator: str = ""
    url: str
    like_count: int = Field(default=0, ge=0)
    platform: Literal["douyin"] = "douyin"


class SearchLaunch(BaseModel):
    platform: Literal["douyin"]
    label: str
    url: str


class ExternalVideoSearchResponse(BaseModel):
    query: str
    provider: Literal["douyin", "platform_search"]
    configured: bool
    videos: list[ExternalVideo] = Field(default_factory=list)
    launches: list[SearchLaunch] = Field(default_factory=list)
    message: str


class MetricDetail(BaseModel):
    kind: MetricKind
    score: float = Field(ge=0)
    normalized_score: float = Field(ge=0, le=1)
    body_part: str
    phase: str
    human_value: str


class Diagnosis(BaseModel):
    action_id: str
    status: DiagnosisStatus = "issue_detected"
    phase: str
    primary_metric: MetricKind
    primary_error: str
    body_part: str
    overall_feedback: str = ""
    priority_feedback: str
    drill: str
    confidence: float = Field(ge=0, le=1)
    timing_offset_seconds: float = 0.0
    trajectory_error: float = 0.0
    angle_error_degrees: float = 0.0
    metrics: list[MetricDetail]
    user_focus: FocusKind = "auto"
    search_query: str = ""
    search_results: list[Tutorial] = Field(default_factory=list)
    tutorial: Tutorial | None = None  # 向后兼容：等于 search_results[0]
    vlm_summary: str | None = None


class Improvement(BaseModel):
    baseline_analysis_id: str
    current_analysis_id: str
    improved: bool
    improvement_percent: float
    message: str


class AnalysisResult(BaseModel):
    id: str
    session_id: str
    action_id: str
    created_at: datetime
    duration_seconds: float
    analyzed_frame_count: int = 0
    pose_coverage: float
    mirrored_input: bool
    trigger_source: str = "feed_pause"
    source_timestamp_seconds: float | None = None
    source_feed_duration_seconds: float | None = None
    source_context_start_seconds: float | None = None
    source_context_end_seconds: float | None = None
    source_phase: str | None = None
    reference_source: Literal["registered_reference", "feed_pause_context"] = (
        "registered_reference"
    )
    diagnosis: Diagnosis
    comparison_image_url: str | None = None
    comparison_video_url: str | None = None
    improvement: Improvement | None = None
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    reference_actions_ready: int
    total_actions: int
    doubao_configured: bool

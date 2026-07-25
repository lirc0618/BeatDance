from pathlib import Path

import numpy as np

from app.schemas import TeachingPlan, TeachingPlanProvenance, TeachingSegment
from app.services.pose import PoseSequence
from app.services.teaching_plans import (
    TeachingPlanService,
    TeachingPlanSource,
    TeachingPlanStore,
)


def teaching_source(tmp_path: Path, source_hash: str = "source-v1") -> TeachingPlanSource:
    video = tmp_path / "reference.mp4"
    video.write_bytes(b"reference-video")
    pose = PoseSequence(
        landmarks=np.zeros((3, 33, 4), dtype=np.float32),
        frame_times=np.array([0.0, 1.0, 2.0], dtype=np.float32),
        source_fps=15.0,
        duration_seconds=3.0,
        coverage=1.0,
    )
    return TeachingPlanSource(
        action_id="groove_step",
        action_name="爱你",
        reference_video=video,
        pose=pose,
        source_hash=source_hash,
        source_start_seconds=8.5,
        source_end_seconds=11.5,
        default_focus="hands",
    )


class RecordingGenerator:
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        self.calls += 1
        return TeachingPlan(
            action_id=source.action_id,
            source_hash=source.source_hash,
            source_start_seconds=source.source_start_seconds,
            source_end_seconds=source.source_end_seconds,
            overall_summary="先拆手势，再接完整动作。",
            segments=[
                TeachingSegment(
                    start_seconds=8.5,
                    end_seconds=10.0,
                    title="手势进入",
                    description="双手先到胸前。",
                    mnemonic="先收，再开。",
                    pitfall="不要提前甩手。",
                    priority="优先",
                    suggested_focus="hands",
                    metric="timing",
                    body_part="双手",
                ),
                TeachingSegment(
                    start_seconds=10.0,
                    end_seconds=11.5,
                    title="手势打开",
                    description="双手向两侧展开。",
                    mnemonic="打开后停住。",
                    pitfall="掌心方向不要翻反。",
                    priority="建议",
                    suggested_focus="hands",
                    metric="trajectory",
                    body_part="双手",
                ),
            ],
            warmups=["活动手腕"],
            practice_plan="每段三遍，再连起来。",
            provenance=TeachingPlanProvenance(generator="test", model="stub"),
        )


class FailingGenerator:
    configured = True

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        raise TimeoutError("qwen timeout")


def test_plan_is_cached_and_selected_by_feed_timestamp(tmp_path: Path) -> None:
    generator = RecordingGenerator()
    service = TeachingPlanService(TeachingPlanStore(tmp_path / "plans"), generator)
    source = teaching_source(tmp_path)

    first = service.prepare(source)
    second = service.prepare(source)
    selected = service.segment_for(
        source.action_id,
        10.5,
        expected_source_hash=source.source_hash,
    )

    assert first == second
    assert generator.calls == 1
    assert selected is not None
    assert selected.title == "手势打开"


def test_generation_failure_falls_back_without_using_a_stale_plan(tmp_path: Path) -> None:
    store = TeachingPlanStore(tmp_path / "plans")
    first_source = teaching_source(tmp_path, source_hash="source-v1")
    TeachingPlanService(store, RecordingGenerator()).prepare(first_source)
    replacement = teaching_source(tmp_path, source_hash="source-v2")

    result = TeachingPlanService(store, FailingGenerator()).prepare(replacement)
    selected = TeachingPlanService(store, FailingGenerator()).segment_for(
        replacement.action_id,
        10.5,
        expected_source_hash=replacement.source_hash,
    )

    assert result is None
    assert selected is None

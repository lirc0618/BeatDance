import json
import threading
from pathlib import Path

import httpx
import numpy as np

from app.config import Settings
from app.schemas import TeachingPlan, TeachingPlanProvenance, TeachingSegment
from app.services.diagnosis import ActionRegistry
from app.services.pause_coach import PauseCoach
from app.services.pose import PoseSequence
from app.services.teaching_plans import (
    QwenTeachingPlanGenerator,
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


def generated_plan(source: TeachingPlanSource) -> TeachingPlan:
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


class RecordingGenerator:
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        self.calls += 1
        return generated_plan(source)


class FailingGenerator:
    configured = True

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        raise TimeoutError("qwen timeout")


class BlockingGenerator(RecordingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.first_entered = threading.Event()
        self.second_entered = threading.Event()
        self.release = threading.Event()

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        self.calls += 1
        if self.calls == 1:
            self.first_entered.set()
        else:
            self.second_entered.set()
        self.release.wait(timeout=2)
        return generated_plan(source)


class ReplacementGenerator:
    configured = True

    def __init__(self) -> None:
        self.first_entered = threading.Event()
        self.release_first = threading.Event()

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        if source.source_hash == "source-v1":
            self.first_entered.set()
            self.release_first.wait(timeout=2)
        return generated_plan(source)


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
    boundary = service.segment_for(
        source.action_id,
        10.0,
        expected_source_hash=source.source_hash,
    )

    assert first == second
    assert generator.calls == 1
    assert selected is not None
    assert selected.title == "手势打开"
    assert boundary is not None
    assert boundary.title == "手势打开"


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


def test_concurrent_requests_for_the_same_reference_use_single_flight(tmp_path: Path) -> None:
    generator = BlockingGenerator()
    service = TeachingPlanService(TeachingPlanStore(tmp_path / "plans"), generator)
    source = teaching_source(tmp_path)
    first = threading.Thread(target=service.prepare, args=(source,))
    second = threading.Thread(target=service.prepare, args=(source,))

    first.start()
    assert generator.first_entered.wait(timeout=1)
    second.start()
    duplicate_started = generator.second_entered.wait(timeout=0.3)
    generator.release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert duplicate_started is False
    assert generator.calls == 1


def test_new_reference_cannot_be_overwritten_by_an_older_background_task(
    tmp_path: Path,
) -> None:
    generator = ReplacementGenerator()
    store = TeachingPlanStore(tmp_path / "plans")
    service = TeachingPlanService(store, generator)
    old_source = teaching_source(tmp_path, source_hash="source-v1")
    new_source = teaching_source(tmp_path, source_hash="source-v2")
    first = threading.Thread(target=service.prepare, args=(old_source,))
    second = threading.Thread(target=service.prepare, args=(new_source,))

    first.start()
    assert generator.first_entered.wait(timeout=1)
    second.start()
    generator.release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    stored = store.load(old_source.action_id)
    assert stored is not None
    assert stored.source_hash == "source-v2"


def test_qwen_generator_normalizes_model_output_to_feed_timestamps(tmp_path: Path) -> None:
    content = """```json
    {
      "overall_summary": "先收手，再向外打开。",
      "segments": [
        {
          "start_time": 0,
          "end_time": 1.5,
          "title": "双手收回",
          "description": "双手回到胸前。",
          "mnemonic": "收到胸口",
          "pitfall": "肩膀不要抬起",
          "priority": "优先",
          "suggested_focus": "hands",
          "metric": "timing",
          "body_part": "双手"
        },
        {
          "start_time": 1.5,
          "end_time": 3,
          "title": "双手打开",
          "description": "双手向两侧展开。",
          "mnemonic": "开到两边",
          "pitfall": "不要翻掌",
          "priority": "建议",
          "suggested_focus": "hands",
          "metric": "trajectory",
          "body_part": "双手"
        }
      ],
      "warm_up_tips": ["活动手腕"],
      "practice_plan": "每段练三遍。",
      "image_generation_prompt": "保留但暂不生成图片"
    }
    ```"""

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-qwen-key"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        dashscope_api_key="test-qwen-key",
        qwen_send_images=False,
    )
    generator = QwenTeachingPlanGenerator(
        settings,
        transport=httpx.MockTransport(respond),
    )

    plan = generator.generate(teaching_source(tmp_path))

    assert plan.segments[0].start_seconds == 8.5
    assert plan.segments[1].end_seconds == 11.5
    assert plan.segments[0].metric == "timing"
    assert plan.image_prompt == "保留但暂不生成图片"


def test_pause_coach_uses_plan_inside_its_reference_window(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    built_in = json.loads(
        (root / "backend" / "app" / "data" / "actions.json").read_text(encoding="utf-8")
    )
    built_in["actions"][0]["teaching_source_hash"] = "source-v1"
    registry_path = tmp_path / "actions.json"
    registry_path.write_text(json.dumps(built_in, ensure_ascii=False), encoding="utf-8")
    service = TeachingPlanService(
        TeachingPlanStore(tmp_path / "plans"),
        RecordingGenerator(),
    )
    service.prepare(teaching_source(tmp_path, source_hash="source-v1"))
    coach = PauseCoach(
        ActionRegistry(registry_path),
        root / "assets" / "samples" / "open_sources",
        tmp_path / "contexts",
        teaching_plans=service,
    )

    enhanced = coach.explain("groove_step", timestamp_seconds=10.5)
    fallback = coach.explain("groove_step", timestamp_seconds=4.0)

    assert enhanced.phase == "手势打开"
    assert enhanced.likely_stuck_at == "双手向两侧展开。易错点：掌心方向不要翻反。"
    assert enhanced.watch_for == "打开后停住。"
    assert fallback.phase != "手势打开"


def test_invalid_qwen_json_is_rejected_without_storing_a_plan(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "这不是 JSON"}}]},
        )

    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        dashscope_api_key="test-qwen-key",
        qwen_send_images=False,
    )
    store = TeachingPlanStore(tmp_path / "plans")
    service = TeachingPlanService(
        store,
        QwenTeachingPlanGenerator(settings, transport=httpx.MockTransport(respond)),
    )
    source = teaching_source(tmp_path)

    result = service.prepare(source)

    assert result is None
    assert store.load(source.action_id) is None


def test_teaching_plan_storage_does_not_change_five_presets_or_tutorial_counts(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    registry = ActionRegistry(root / "backend" / "app" / "data" / "actions.json")
    before = [(action["id"], len(action["tutorials"])) for action in registry.list()]
    service = TeachingPlanService(
        TeachingPlanStore(tmp_path / "plans"),
        RecordingGenerator(),
    )

    service.prepare(teaching_source(tmp_path))
    after = [(action["id"], len(action["tutorials"])) for action in registry.list()]

    assert after == before
    assert len(after) == 5
    assert all(tutorial_count == 5 for _, tutorial_count in after)

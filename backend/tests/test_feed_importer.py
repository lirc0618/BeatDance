import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import create_router
from app.config import Settings
from app.services.analyzer import Analyzer
from app.services.diagnosis import ActionRegistry
from app.services.feed_importer import FeedImporter, FeedImportSpec
from app.services.pause_coach import PauseCoach
from app.services.teaching_plans import QwenTeachingPlanGenerator
from app.services.video import VideoValidationError, probe_video


def runtime_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        target_fps=8,
        admin_token="test-secret-that-is-long-enough",
    )
    settings.ensure_directories()
    shutil.copy2(
        Path(__file__).parents[1] / "app" / "data" / "actions.json",
        settings.data_dir / "actions.json",
    )
    return settings


def test_imported_feed_is_immediately_available_as_an_additional_action(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    stale_reader = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "breakdance_2_step.mp4"

    result = importer.import_video(
        source,
        FeedImportSpec(
            action_id="demo_extra",
            name="额外测试动作",
            pause_at_seconds=3.0,
            creator="@测试素材",
        ),
    )

    assert result.created is True
    assert result.action["id"] == "demo_extra"
    assert len(registry.list()) == 6
    assert stale_reader.get("demo_extra")["name"] == "额外测试动作"
    stored = registry.get("demo_extra")
    feed_name = Path(stored["feed_video_url"]).name
    assert (settings.feed_dir / feed_name).is_file()
    assert stored["cover_url"].startswith("/media/covers/")
    cover_name = Path(stored["cover_url"]).name
    cover = settings.covers_dir / cover_name
    assert cover.is_file()
    assert cover.stat().st_size > 0
    manifest = json.loads(
        (settings.references_dir / stored["reference_manifest"]).read_text(encoding="utf-8")
    )
    assert (settings.references_dir / manifest["video"]).is_file()
    assert (settings.references_dir / manifest["sequence"]).is_file()
    assert Analyzer(settings).reference_ready("demo_extra") is True
    insight = PauseCoach(
        registry,
        settings.feed_dir,
        settings.pause_contexts_dir,
    ).explain("demo_extra", timestamp_seconds=3.0)
    assert insight.sampled_frame_count > 0
    assert len(insight.search_results) == 3


def test_imported_feed_keeps_its_audio_track(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    sample = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "simple_step.mp4"
    source = tmp_path / "with-audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(sample),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )

    result = importer.import_video(
        source,
        FeedImportSpec(action_id="audio_move", name="有声动作"),
    )
    feed = settings.feed_dir / Path(result.action["feed_video_url"]).name
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=nw=1:nk=1",
            str(feed),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert probe.stdout.strip() == "aac"


def test_importing_the_same_id_replaces_the_catalog_entry(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    samples = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    first = importer.import_video(
        samples / "breakdance_2_step.mp4",
        FeedImportSpec(action_id="my_move", name="旧动作"),
    )

    replacement = importer.import_video(
        samples / "simple_step.mp4",
        FeedImportSpec(action_id="my_move", name="新动作"),
    )
    third = importer.import_video(
        samples / "breakdance_2_step.mp4",
        FeedImportSpec(action_id="my_move", name="第三版动作"),
    )

    assert replacement.created is False
    assert third.created is False
    assert len(registry.list()) == 6
    assert registry.get("my_move")["name"] == "第三版动作"
    assert registry.get("my_move")["feed_video_url"] != first.action["feed_video_url"]
    assert not (settings.feed_dir / Path(first.action["feed_video_url"]).name).exists()
    assert len(list(settings.feed_dir.glob("my_move-*.mp4"))) == 2
    assert len(list(settings.references_dir.glob("my_move-*"))) == 6
    assert Analyzer(settings).reference_ready("my_move") is True


def test_failed_replacement_keeps_the_previous_action_usable(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "simple_step.mp4"
    importer.import_video(
        source,
        FeedImportSpec(action_id="safe_move", name="可用动作"),
    )
    previous = json.loads(json.dumps(registry.get("safe_move")))
    feed_files = set(settings.feed_dir.iterdir())
    reference_files = set(settings.references_dir.iterdir())

    with pytest.raises(VideoValidationError, match="参考时间点"):
        importer.import_video(
            source,
            FeedImportSpec(
                action_id="safe_move",
                name="损坏替换",
                pause_at_seconds=999,
            ),
        )

    assert registry.get("safe_move") == previous
    assert set(settings.feed_dir.iterdir()) == feed_files
    assert set(settings.references_dir.iterdir()) == reference_files
    assert Analyzer(settings).reference_ready("safe_move") is True


def test_cleanup_failure_does_not_rollback_a_committed_import(tmp_path, monkeypatch):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "simple_step.mp4"

    def fail_cleanup(*args, **kwargs):
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(importer, "_prune_old_generations", fail_cleanup)
    result = importer.import_video(
        source,
        FeedImportSpec(action_id="cleanup_safe", name="清理失败仍可用"),
    )

    assert result.created is True
    assert registry.get("cleanup_safe")["name"] == "清理失败仍可用"
    assert (settings.feed_dir / Path(result.action["feed_video_url"]).name).is_file()
    assert Analyzer(settings).reference_ready("cleanup_safe") is True


def test_post_commit_version_failure_keeps_the_new_generation(tmp_path, monkeypatch):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "simple_step.mp4"
    original_file_version = registry._file_version

    def fail_only_after_commit():
        payload = json.loads(settings.action_registry_path.read_text(encoding="utf-8"))
        if any(action["id"] == "post_commit_safe" for action in payload["actions"]):
            raise OSError("simulated post-commit stat failure")
        return original_file_version()

    monkeypatch.setattr(registry, "_file_version", fail_only_after_commit)
    result = importer.import_video(
        source,
        FeedImportSpec(action_id="post_commit_safe", name="提交后仍可用"),
    )
    monkeypatch.setattr(registry, "_file_version", original_file_version)

    assert result.created is True
    assert registry.get("post_commit_safe")["name"] == "提交后仍可用"
    assert (settings.feed_dir / Path(result.action["feed_video_url"]).name).is_file()
    assert Analyzer(settings).reference_ready("post_commit_safe") is True


def test_authenticated_http_import_publishes_the_action(tmp_path):
    settings = runtime_settings(tmp_path)
    settings.admin_token = "replace-with-a-long-random-secret"
    assert settings.admin_mutations_enabled is False
    settings.admin_token = "test-secret-that-is-long-enough"
    analyzer = Analyzer(settings)
    teaching_requests: list[str] = []
    analyzer.teaching_plans.prepare = lambda source: teaching_requests.append(source.action_id)
    app = FastAPI()
    app.include_router(
        create_router(settings, analyzer),
        prefix=settings.api_prefix,
    )
    client = TestClient(app)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "breakdance_2_step.mp4"
    form = {
        "action_id": "http_move",
        "name": "接口导入动作",
        "pause_at_seconds": "3",
        "focus": "hands",
    }

    settings.admin_token = ""
    with source.open("rb") as handle:
        disabled = client.post(
            f"{settings.api_prefix}/actions/import",
            data=form,
            files={"video": ("move.mp4", handle, "video/mp4")},
        )
    assert disabled.status_code == 503
    settings.admin_token = "test-secret-that-is-long-enough"

    with source.open("rb") as handle:
        unauthorized = client.post(
            f"{settings.api_prefix}/actions/import",
            data=form,
            files={"video": ("move.mp4", handle, "video/mp4")},
        )
    assert unauthorized.status_code == 401

    with source.open("rb") as handle:
        imported = client.post(
            f"{settings.api_prefix}/actions/import",
            data=form,
            files={"video": ("move.mp4", handle, "video/mp4")},
            headers={"X-Admin-Token": "test-secret-that-is-long-enough"},
        )

    assert imported.status_code == 200
    assert imported.json()["created"] is True
    actions = client.get(f"{settings.api_prefix}/actions").json()
    assert any(action["id"] == "http_move" and action["reference_ready"] for action in actions)
    assert next(action for action in actions if action["id"] == "http_move")["skill_focus"] == "手势关"
    assert next(action for action in actions if action["id"] == "groove_step")["skill_focus"] == "手势关"

    insight = client.post(
        f"{settings.api_prefix}/actions/http_move/pause-insight",
        json={"timestamp_seconds": 3},
    )
    assert insight.status_code == 200
    assert insight.json()["sampled_frame_count"] > 0

    wrong_dance = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "arm_movements_reference.mp4"
    )
    matching_context = tmp_path / "matching-context.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "1.5",
            "-t",
            "3",
            "-i",
            str(source),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(matching_context),
        ],
        check=True,
    )
    with wrong_dance.open("rb") as handle:
        mismatched = client.post(
            f"{settings.api_prefix}/analyze",
            data={
                "action_id": "http_move",
                "session_id": "dynamic-http-test",
                "pause_timestamp_seconds": "3",
            },
            files={"video": ("wrong-dance.mp4", handle, "video/mp4")},
        )
    assert mismatched.status_code == 422
    assert "这段动作和《接口导入动作》对不上" in mismatched.json()["detail"]

    with matching_context.open("rb") as handle:
        analyzed = client.post(
            f"{settings.api_prefix}/analyze",
            data={
                "action_id": "http_move",
                "session_id": "dynamic-http-test",
                "pause_timestamp_seconds": "3",
            },
            files={"video": ("attempt.mp4", handle, "video/mp4")},
        )
    assert analyzed.status_code == 200
    analyzed_payload = analyzed.json()
    assert analyzed_payload["reference_source"] == "feed_pause_context"
    assert analyzed_payload["analyzed_frame_count"] > 20
    assert analyzed_payload["comparison_video_url"].startswith("/media/comparison-videos/")
    comparison_video = settings.comparison_videos_dir / f"{analyzed_payload['id']}.mp4"
    assert comparison_video.is_file()
    assert probe_video(comparison_video).duration_seconds == pytest.approx(
        analyzed_payload["duration_seconds"],
        abs=0.15,
    )
    assert client.delete(f"{settings.api_prefix}/results/{analyzed_payload['id']}").status_code == 200
    assert not comparison_video.exists()
    assert teaching_requests == ["http_move"]


def test_http_import_schedules_reference_teaching_after_publish(tmp_path):
    settings = runtime_settings(tmp_path)
    analyzer = Analyzer(settings)
    scheduled: list[str] = []
    analyzer.teaching_plans.prepare = lambda source: scheduled.append(source.action_id)
    app = FastAPI()
    app.include_router(create_router(settings, analyzer), prefix=settings.api_prefix)
    client = TestClient(app)
    source = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "simple_step.mp4"
    )

    with source.open("rb") as handle:
        response = client.post(
            f"{settings.api_prefix}/actions/import",
            data={
                "action_id": "teaching_ready",
                "name": "教学计划测试",
                "pause_at_seconds": "3",
            },
            files={"video": ("move.mp4", handle, "video/mp4")},
            headers={"X-Admin-Token": settings.admin_token},
        )

    assert response.status_code == 200
    assert scheduled == ["teaching_ready"]


def test_reference_upload_schedules_teaching_and_updates_its_source_hash(tmp_path):
    settings = runtime_settings(tmp_path)
    analyzer = Analyzer(settings)
    scheduled: list[str] = []
    analyzer.teaching_plans.prepare = lambda source: scheduled.append(source.action_id)
    app = FastAPI()
    app.include_router(create_router(settings, analyzer), prefix=settings.api_prefix)
    client = TestClient(app)
    source = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "simple_step.mp4"
    )

    with source.open("rb") as handle:
        response = client.post(
            f"{settings.api_prefix}/actions/groove_step/reference",
            files={"video": ("reference.mp4", handle, "video/mp4")},
            headers={"X-Admin-Token": settings.admin_token},
        )

    assert response.status_code == 200
    assert scheduled == ["groove_step"]
    assert analyzer.registry.get("groove_step")["teaching_source_hash"]


def test_qwen_http_timeout_does_not_change_successful_import_response(tmp_path):
    settings = runtime_settings(tmp_path)
    settings.dashscope_api_key = "test-qwen-key"
    settings.qwen_send_images = False

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    analyzer = Analyzer(settings)
    analyzer.teaching_plans.generator = QwenTeachingPlanGenerator(
        settings,
        transport=httpx.MockTransport(timeout),
    )
    app = FastAPI()
    app.include_router(create_router(settings, analyzer), prefix=settings.api_prefix)
    client = TestClient(app)
    source = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "simple_step.mp4"
    )

    with source.open("rb") as handle:
        response = client.post(
            f"{settings.api_prefix}/actions/import",
            data={"action_id": "timeout_safe", "name": "超时仍可用"},
            files={"video": ("move.mp4", handle, "video/mp4")},
            headers={"X-Admin-Token": settings.admin_token},
        )

    assert response.status_code == 200
    assert analyzer.registry.get("timeout_safe")["name"] == "超时仍可用"
    assert analyzer.teaching_plans.store.load("timeout_safe") is None


def test_sample_library_lists_server_videos_and_imports_one_without_upload(tmp_path):
    settings = runtime_settings(tmp_path)
    settings.seed_feed_dir = (
        Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    )
    app = FastAPI()
    app.include_router(
        create_router(settings, Analyzer(settings)),
        prefix=settings.api_prefix,
    )
    client = TestClient(app)

    library = client.get(f"{settings.api_prefix}/sample-library")

    assert library.status_code == 200
    assert len(library.json()) >= 10
    assert all(item["available"] for item in library.json())
    sample = next(item for item in library.json() if item["id"] == "breakdance_2_step")
    assert sample["name"] == "Breaking 两步"
    assert (
        sample["preview_url"]
        == "/api/v1/sample-library/breakdance_2_step/video"
    )
    assert sample["available"] is True
    assert sample["imported"] is False
    preview = client.get(sample["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "video/mp4"

    imported = client.post(
        f"{settings.api_prefix}/sample-library/breakdance_2_step/import",
        headers={"X-Admin-Token": settings.admin_token},
    )

    assert imported.status_code == 200
    assert imported.json()["created"] is True
    assert imported.json()["action"]["id"] == "library_breakdance_2_step"
    refreshed = client.get(f"{settings.api_prefix}/sample-library").json()
    refreshed_sample = next(
        item for item in refreshed if item["id"] == "breakdance_2_step"
    )
    assert refreshed_sample["imported"] is True


def test_startup_removes_only_orphaned_generated_files(tmp_path):
    settings = runtime_settings(tmp_path)
    nonce = "a" * 32
    active_nonce = "b" * 32
    orphan_feed = settings.feed_dir / f"orphan-{nonce}.mp4"
    orphan_reference = settings.references_dir / f"orphan-{nonce}.npz"
    interrupted = settings.feed_dir / ".orphan.pending.mp4"
    user_file = settings.feed_dir / "my-video.mp4"
    active_video = settings.references_dir / f"groove_step-{active_nonce}.mp4"
    active_sequence = settings.references_dir / f"groove_step-{active_nonce}.npz"
    active_manifest = settings.references_dir / "groove_step.current.json"
    for path in (orphan_feed, orphan_reference, interrupted, user_file):
        path.write_bytes(b"test")
    active_video.write_bytes(b"video")
    active_sequence.write_bytes(b"pose")
    active_manifest.write_text(
        json.dumps(
            {
                "video": active_video.name,
                "sequence": active_sequence.name,
            }
        ),
        encoding="utf-8",
    )

    settings.bootstrap_runtime_catalog()

    assert not orphan_feed.exists()
    assert not orphan_reference.exists()
    assert not interrupted.exists()
    assert user_file.exists()
    assert active_video.exists()
    assert active_sequence.exists()
    assert active_manifest.exists()


def test_clean_startup_seeds_the_five_featured_dances_and_feed_files(tmp_path):
    samples = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        seed_feed_dir=samples,
        seed_reference_dir=Path(__file__).parents[2] / "assets" / "references",
    )
    settings.ensure_directories()

    settings.bootstrap_runtime_catalog()

    actions = ActionRegistry(settings.action_registry_path).list()
    assert [action["name"] for action in actions] == [
        "爱你",
        "科目三",
        "摇一摇",
        "Jumpstyle",
        "爵士",
    ]
    assert all(
        (settings.feed_dir / Path(action["feed_video_url"]).name).is_file()
        for action in actions
    )
    assert Analyzer(settings).reference_ready("jazz_demo") is True


def test_upgrade_replaces_the_legacy_fifth_feed_with_jazz_without_overwriting_others(
    tmp_path,
):
    samples = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    references = Path(__file__).parents[2] / "assets" / "references"
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        seed_feed_dir=samples,
        seed_reference_dir=references,
    )
    settings.ensure_directories()
    built_in = json.loads(settings.built_in_action_registry_path.read_text(encoding="utf-8"))
    legacy = {
        **built_in,
        "actions": [
            {**action, "description": "保留旧数据"}
            for action in built_in["actions"]
            if action["id"] != "jazz_demo"
        ] + [
            {
                **built_in["actions"][-1],
                "id": "library_breakdance_2_step",
                "name": "Breaking 两步",
            }
        ],
    }
    runtime_registry = settings.data_dir / "actions.json"
    runtime_registry.write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )

    settings.bootstrap_runtime_catalog()

    actions = ActionRegistry(settings.action_registry_path).list()
    assert [action["id"] for action in actions] == [
        "groove_step",
        "arm_wave",
        "cross_step",
        "two_step_demo",
        "jazz_demo",
    ]
    raw = json.loads(runtime_registry.read_text(encoding="utf-8"))
    assert raw["actions"][0]["description"] == "保留旧数据"
    assert all(
        action["id"] != "library_breakdance_2_step"
        for action in raw["actions"]
    )
    assert Analyzer(settings).reference_ready("jazz_demo") is True


def test_startup_repairs_a_partially_migrated_jazz_action(tmp_path):
    samples = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    references = Path(__file__).parents[2] / "assets" / "references"
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        seed_feed_dir=samples,
        seed_reference_dir=references,
    )
    settings.ensure_directories()
    built_in = json.loads(settings.built_in_action_registry_path.read_text(encoding="utf-8"))
    legacy_manifest = "library_breakdance_2_step-deadbeef.current.json"
    legacy_feed = "/media/feed/library_breakdance_2_step-deadbeef.mp4"
    partially_migrated = {
        **built_in,
        "actions": [
            {
                **action,
                "reference_manifest": legacy_manifest,
                "reference_video_url": "",
                "feed_video_url": legacy_feed,
            }
            if action["id"] == "jazz_demo"
            else action
            for action in built_in["actions"]
        ],
    }
    runtime_registry = settings.data_dir / "actions.json"
    runtime_registry.write_text(
        json.dumps(partially_migrated, ensure_ascii=False),
        encoding="utf-8",
    )

    settings.bootstrap_runtime_catalog()

    jazz = ActionRegistry(settings.action_registry_path).get("jazz_demo")
    assert jazz["reference_manifest"] == "jazz_demo.current.json"
    assert jazz["reference_video_url"] == "/media/references/jazz_demo.mp4"
    assert jazz["feed_video_url"] == "/media/feed/爵士.MP4"
    assert Analyzer(settings).reference_ready("jazz_demo") is True

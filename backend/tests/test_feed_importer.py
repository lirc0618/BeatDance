import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import create_router
from app.config import Settings
from app.services.analyzer import Analyzer
from app.services.diagnosis import ActionRegistry
from app.services.feed_importer import FeedImporter, FeedImportSpec
from app.services.pause_coach import PauseCoach
from app.services.video import VideoValidationError


def runtime_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        target_fps=8,
        admin_token="test-secret",
    )
    settings.ensure_directories()
    shutil.copy2(
        Path(__file__).parents[1] / "app" / "data" / "actions.json",
        settings.data_dir / "actions.json",
    )
    return settings


def test_imported_feed_is_immediately_available_as_a_fourth_action(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "breakdance_2_step.mp4"

    result = importer.import_video(
        source,
        FeedImportSpec(
            action_id="demo_four",
            name="第四条测试动作",
            pause_at_seconds=3.0,
            creator="@测试素材",
        ),
    )

    assert result.created is True
    assert result.action["id"] == "demo_four"
    assert len(registry.list()) == 4
    stored = registry.get("demo_four")
    feed_name = Path(stored["feed_video_url"]).name
    assert (settings.feed_dir / feed_name).is_file()
    manifest = json.loads(
        (settings.references_dir / stored["reference_manifest"]).read_text(encoding="utf-8")
    )
    assert (settings.references_dir / manifest["video"]).is_file()
    assert (settings.references_dir / manifest["sequence"]).is_file()
    assert Analyzer(settings).reference_ready("demo_four") is True
    insight = PauseCoach(
        registry,
        settings.feed_dir,
        settings.pause_contexts_dir,
    ).explain("demo_four", timestamp_seconds=3.0)
    assert insight.sampled_frame_count > 0
    assert len(insight.search_results) == 3


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
    assert len(registry.list()) == 4
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


def test_authenticated_http_import_publishes_the_action(tmp_path):
    settings = runtime_settings(tmp_path)
    app = FastAPI()
    app.include_router(
        create_router(settings, Analyzer(settings)),
        prefix=settings.api_prefix,
    )
    client = TestClient(app)
    source = Path(__file__).parents[2] / "assets" / "samples" / "open_sources" / "breakdance_2_step.mp4"
    form = {
        "action_id": "http_move",
        "name": "接口导入动作",
        "pause_at_seconds": "3",
    }

    settings.admin_token = "change-me"
    with source.open("rb") as handle:
        disabled = client.post(
            f"{settings.api_prefix}/actions/import",
            data=form,
            files={"video": ("move.mp4", handle, "video/mp4")},
            headers={"X-Admin-Token": "change-me"},
        )
    assert disabled.status_code == 503
    settings.admin_token = "test-secret"

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
            headers={"X-Admin-Token": "test-secret"},
        )

    assert imported.status_code == 200
    assert imported.json()["created"] is True
    actions = client.get(f"{settings.api_prefix}/actions").json()
    assert any(action["id"] == "http_move" and action["reference_ready"] for action in actions)


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

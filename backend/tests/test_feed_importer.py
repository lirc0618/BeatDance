import json
import shutil
from pathlib import Path

import pytest

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
    source = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "breakdance_2_step.mp4"
    )

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
        (settings.references_dir / stored["reference_manifest"]).read_text(
            encoding="utf-8"
        )
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

    assert replacement.created is False
    assert len(registry.list()) == 4
    assert registry.get("my_move")["name"] == "新动作"
    assert (
        registry.get("my_move")["feed_video_url"]
        != first.action["feed_video_url"]
    )
    assert Analyzer(settings).reference_ready("my_move") is True


def test_failed_replacement_keeps_the_previous_action_usable(tmp_path):
    settings = runtime_settings(tmp_path)
    registry = ActionRegistry(settings.action_registry_path)
    importer = FeedImporter(settings, registry)
    source = (
        Path(__file__).parents[2]
        / "assets"
        / "samples"
        / "open_sources"
        / "simple_step.mp4"
    )
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

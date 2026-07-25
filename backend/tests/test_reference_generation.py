from pathlib import Path

import numpy as np

from app.config import Settings
from app.services.analyzer import Analyzer
from app.services.pose import PoseSequence


def test_reference_switches_with_one_atomic_generation_pointer(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=Path(__file__).parents[2] / "assets" / "samples" / "open_sources",
    )
    settings.ensure_directories()
    analyzer = Analyzer(settings)
    pose = PoseSequence(
        landmarks=np.zeros((3, 33, 4), dtype=np.float32),
        frame_times=np.array([0.0, 0.1, 0.2], dtype=np.float32),
        source_fps=10.0,
        duration_seconds=3.0,
        coverage=1.0,
    )
    monkeypatch.setattr(
        "app.services.analyzer.extract_pose_sequence",
        lambda *args, **kwargs: pose,
    )
    source = tmp_path / "reference.mp4"
    source.write_bytes(b"complete-video-generation")

    analyzer.register_reference("groove_step", source)

    video, sequence = analyzer.reference_paths("groove_step")
    assert video.read_bytes() == b"complete-video-generation"
    assert PoseSequence.load(sequence).coverage == 1.0
    assert analyzer.reference_video_url("groove_step").endswith(video.name)
    first_generation = (video, sequence)

    # A crash before publishing the manifest can leave an orphan generation,
    # but readers continue using the last complete pair.
    (settings.references_dir / "groove_step-orphan.mp4").write_bytes(b"partial")
    assert analyzer.reference_paths("groove_step") == first_generation

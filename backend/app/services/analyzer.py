from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..schemas import AnalysisResult, FocusKind, Improvement, PauseInsight
from .diagnosis import ActionRegistry, calculate_improvement, compare_poses
from .doubao import DoubaoService
from .dtw import dynamic_time_warping
from .features import normalize_pose, pose_feature_matrix
from .pause_coach import PauseCoach
from .pose import PoseSequence, extract_pose_sequence, mirror_sequence
from .render import create_comparison_image
from .storage import ResultStore


class ReferenceNotReadyError(RuntimeError):
    pass


class Analyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = ActionRegistry(settings.action_registry_path)
        self.pause_coach = PauseCoach(
            self.registry,
            settings.feed_dir,
            settings.pause_contexts_dir,
        )
        self.store = ResultStore(settings.results_dir)
        self.doubao = DoubaoService(settings)
        self.reference_lock = threading.RLock()

    def reference_manifest_path(self, action_id: str) -> Path:
        action = self.registry.get(action_id)
        manifest_name = str(action.get("reference_manifest", f"{action_id}.current.json"))
        if Path(manifest_name).name != manifest_name:
            raise ValueError("参考清单文件名无效")
        return self.settings.references_dir / manifest_name

    def reference_paths(self, action_id: str) -> tuple[Path, Path]:
        manifest = self.reference_manifest_path(action_id)
        if manifest.exists():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                video_name = str(payload["video"])
                sequence_name = str(payload["sequence"])
                if Path(video_name).name == video_name and Path(sequence_name).name == sequence_name:
                    generation_paths = (
                        self.settings.references_dir / video_name,
                        self.settings.references_dir / sequence_name,
                    )
                    if all(path.is_file() for path in generation_paths):
                        return generation_paths
            except (KeyError, OSError, json.JSONDecodeError, TypeError):
                pass
        return (
            self.settings.references_dir / f"{action_id}.mp4",
            self.settings.references_dir / f"{action_id}.npz",
        )

    def reference_video_url(self, action_id: str) -> str:
        with self.reference_lock:
            video, sequence = self.reference_paths(action_id)
            if not video.is_file() or not sequence.is_file():
                return ""
            return f"/media/references/{video.name}"

    def reference_ready(self, action_id: str) -> bool:
        with self.reference_lock:
            video, sequence = self.reference_paths(action_id)
            return video.exists() and sequence.exists()

    def analysis_reference(
        self,
        action_id: str,
        pause_insight: PauseInsight | None,
    ) -> tuple[Path, PoseSequence, str]:
        if pause_insight is None:
            video, sequence_path = self.reference_paths(action_id)
            return video, PoseSequence.load(sequence_path), "registered_reference"

        video = self.pause_coach.extract_context(action_id, pause_insight)
        sequence_path = video.with_suffix(".npz")
        if sequence_path.exists():
            sequence = PoseSequence.load(sequence_path)
        else:
            sequence = extract_pose_sequence(
                video,
                target_fps=self.settings.target_fps,
                model_complexity=self.settings.pose_model_complexity,
                min_detection_confidence=self.settings.pose_min_detection_confidence,
                min_tracking_confidence=self.settings.pose_min_tracking_confidence,
            )
            pending = sequence_path.with_name(f".{sequence_path.stem}-{uuid4().hex}.pending.npz")
            try:
                sequence.save(pending)
                pending.replace(sequence_path)
            finally:
                pending.unlink(missing_ok=True)
        if sequence.coverage < self.settings.min_pose_coverage:
            raise ValueError(
                f"暂停片段人体识别覆盖率仅 {sequence.coverage:.0%}，请换一个人物全身清晰的时刻。"
            )
        return video, sequence, "feed_pause_context"

    def register_reference(self, action_id: str, video_path: Path) -> PoseSequence:
        self.registry.get(action_id)
        pose = extract_pose_sequence(
            video_path,
            target_fps=self.settings.target_fps,
            model_complexity=self.settings.pose_model_complexity,
            min_detection_confidence=self.settings.pose_min_detection_confidence,
            min_tracking_confidence=self.settings.pose_min_tracking_confidence,
        )
        if pose.coverage < self.settings.min_pose_coverage:
            raise ValueError(f"参考视频人体识别覆盖率不足：{pose.coverage:.0%}")

        nonce = uuid4().hex
        target_video = self.settings.references_dir / f"{action_id}-{nonce}.mp4"
        target_sequence = self.settings.references_dir / f"{action_id}-{nonce}.npz"
        manifest = self.reference_manifest_path(action_id)
        pending_video = target_video.with_name(f".{target_video.name}.pending.mp4")
        pending_sequence = target_sequence.with_name(f".{target_sequence.name}.pending.npz")
        pending_manifest = manifest.with_name(f".{manifest.name}-{nonce}.pending")
        try:
            pending_video.write_bytes(video_path.read_bytes())
            pose.save(pending_sequence)
            pending_video.replace(target_video)
            pending_sequence.replace(target_sequence)
            pending_manifest.write_text(
                json.dumps(
                    {
                        "generation": nonce,
                        "video": target_video.name,
                        "sequence": target_sequence.name,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.reference_lock:
                pending_manifest.replace(manifest)
        finally:
            pending_video.unlink(missing_ok=True)
            pending_sequence.unlink(missing_ok=True)
            pending_manifest.unlink(missing_ok=True)
        return pose

    async def analyze(
        self,
        action_id: str,
        session_id: str,
        video_path: Path,
        baseline_analysis_id: str | None = None,
        focus: FocusKind = "auto",
        pause_insight: PauseInsight | None = None,
    ) -> AnalysisResult:
        action = self.registry.get(action_id)
        candidate_sequence = extract_pose_sequence(
            video_path,
            target_fps=self.settings.target_fps,
            model_complexity=self.settings.pose_model_complexity,
            min_detection_confidence=self.settings.pose_min_detection_confidence,
            min_tracking_confidence=self.settings.pose_min_tracking_confidence,
        )
        if candidate_sequence.coverage < self.settings.min_pose_coverage:
            raise ValueError(
                f"人体识别覆盖率仅 {candidate_sequence.coverage:.0%}。请保证单人全身入镜、光线充足、固定机位。"
            )

        with self.reference_lock:
            if not self.reference_ready(action_id):
                raise ReferenceNotReadyError(f"动作 {action_id} 尚未上传参考视频")
            reference_video, reference_sequence, reference_source = self.analysis_reference(
                action_id, pause_insight
            )
            ref_normalized = normalize_pose(reference_sequence)
            normal = normalize_pose(candidate_sequence)
            mirrored_sequence = mirror_sequence(candidate_sequence)
            mirrored_normalized = normalize_pose(mirrored_sequence)

            normal_cost = dynamic_time_warping(
                pose_feature_matrix(ref_normalized),
                pose_feature_matrix(normal),
            ).normalized_cost
            mirrored_cost = dynamic_time_warping(
                pose_feature_matrix(ref_normalized),
                pose_feature_matrix(mirrored_normalized),
            ).normalized_cost
            use_mirror = mirrored_cost + 0.01 < normal_cost
            selected_sequence = mirrored_sequence if use_mirror else candidate_sequence
            selected_normalized = mirrored_normalized if use_mirror else normal

            bundle = compare_poses(
                action_id,
                ref_normalized,
                selected_normalized,
                self.registry,
                use_mirror,
                focus=focus,
            )

            analysis_id = uuid4().hex
            visualization_path = self.settings.visualizations_dir / f"{analysis_id}.jpg"
            rendered = create_comparison_image(
                reference_video=reference_video,
                candidate_video=video_path,
                reference_pose=reference_sequence,
                candidate_pose=selected_sequence,
                reference_frame_index=bundle.key_reference_frame,
                candidate_frame_index=bundle.key_candidate_frame,
                highlight=bundle.diagnosis.body_part,
                output_path=visualization_path,
                mirror_candidate_frame=use_mirror,
            )
        comparison_url = f"/media/visualizations/{rendered.name}" if rendered else None
        if bundle.diagnosis.status == "issue_detected":
            bundle.diagnosis.vlm_summary = await self.doubao.refine_feedback(
                bundle.diagnosis, action["name"], rendered
            )

        improvement = None
        if baseline_analysis_id:
            baseline = self.store.load(baseline_analysis_id)
            if baseline.action_id != action_id or baseline.session_id != session_id:
                raise ValueError("二次练习必须与首次分析使用同一动作和匿名会话")
            improved, percentage = calculate_improvement(baseline.diagnosis, bundle.diagnosis)
            improvement = Improvement(
                baseline_analysis_id=baseline_analysis_id,
                current_analysis_id=analysis_id,
                improved=improved,
                improvement_percent=round(percentage, 1),
                message=(
                    (
                        "这次已经没有明显主导偏差，可以把完整动作加回来。"
                        if bundle.diagnosis.status == "aligned"
                        else f"这次关键偏差降低约 {percentage:.0f}% ，可以把完整动作加回来。"
                    )
                    if improved
                    else "这次变化还不明显。继续只练当前卡点，再录一次。"
                ),
            )

        warnings: list[str] = []
        if use_mirror:
            warnings.append("系统检测到镜像画面，已自动进行左右校正。")
        if candidate_sequence.coverage < 0.8:
            warnings.append("部分帧关键点置信度较低，建议光线更亮并保持全身入镜。")

        result = AnalysisResult(
            id=analysis_id,
            session_id=session_id,
            action_id=action_id,
            created_at=datetime.now(UTC),
            duration_seconds=candidate_sequence.duration_seconds,
            pose_coverage=candidate_sequence.coverage,
            mirrored_input=use_mirror,
            trigger_source="feed_pause",
            source_timestamp_seconds=pause_insight.timestamp_seconds if pause_insight else None,
            source_feed_duration_seconds=(pause_insight.feed_duration_seconds if pause_insight else None),
            source_context_start_seconds=(pause_insight.context_start_seconds if pause_insight else None),
            source_context_end_seconds=(pause_insight.context_end_seconds if pause_insight else None),
            source_phase=pause_insight.phase if pause_insight else None,
            reference_source=reference_source,
            diagnosis=bundle.diagnosis,
            comparison_image_url=comparison_url,
            improvement=improvement,
            warnings=warnings,
        )
        self.store.save(result)
        return result

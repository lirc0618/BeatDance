from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..schemas import AnalysisResult, FocusKind, Improvement
from .diagnosis import ActionRegistry, compare_poses, composite_score
from .doubao import DoubaoService
from .features import normalize_pose, pose_feature_matrix
from .dtw import dynamic_time_warping
from .pose import PoseSequence, extract_pose_sequence, mirror_sequence
from .render import create_comparison_image
from .storage import ResultStore


class ReferenceNotReadyError(RuntimeError):
    pass


class Analyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = ActionRegistry(settings.action_registry_path)
        self.store = ResultStore(settings.results_dir)
        self.doubao = DoubaoService(settings)

    def reference_paths(self, action_id: str) -> tuple[Path, Path]:
        return (
            self.settings.references_dir / f"{action_id}.mp4",
            self.settings.references_dir / f"{action_id}.npz",
        )

    def reference_ready(self, action_id: str) -> bool:
        video, sequence = self.reference_paths(action_id)
        return video.exists() and sequence.exists()

    def register_reference(self, action_id: str, video_path: Path) -> PoseSequence:
        self.registry.get(action_id)
        target_video, target_sequence = self.reference_paths(action_id)
        target_video.write_bytes(video_path.read_bytes())
        pose = extract_pose_sequence(
            target_video,
            target_fps=self.settings.target_fps,
            model_complexity=self.settings.pose_model_complexity,
            min_detection_confidence=self.settings.pose_min_detection_confidence,
            min_tracking_confidence=self.settings.pose_min_tracking_confidence,
        )
        if pose.coverage < self.settings.min_pose_coverage:
            target_video.unlink(missing_ok=True)
            raise ValueError(f"参考视频人体识别覆盖率不足：{pose.coverage:.0%}")
        pose.save(target_sequence)
        return pose

    async def analyze(
        self,
        action_id: str,
        session_id: str,
        video_path: Path,
        baseline_analysis_id: str | None = None,
        focus: FocusKind = "auto",
    ) -> AnalysisResult:
        action = self.registry.get(action_id)
        reference_video, reference_sequence_path = self.reference_paths(action_id)
        if not self.reference_ready(action_id):
            raise ReferenceNotReadyError(f"动作 {action_id} 尚未上传参考视频")

        reference_sequence = PoseSequence.load(reference_sequence_path)
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

        ref_normalized = normalize_pose(reference_sequence)
        normal = normalize_pose(candidate_sequence)
        mirrored_sequence = mirror_sequence(candidate_sequence)
        mirrored_normalized = normalize_pose(mirrored_sequence)

        normal_cost = dynamic_time_warping(pose_feature_matrix(ref_normalized), pose_feature_matrix(normal)).normalized_cost
        mirrored_cost = dynamic_time_warping(
            pose_feature_matrix(ref_normalized), pose_feature_matrix(mirrored_normalized)
        ).normalized_cost
        use_mirror = mirrored_cost + 0.01 < normal_cost
        selected_sequence = mirrored_sequence if use_mirror else candidate_sequence
        selected_normalized = mirrored_normalized if use_mirror else normal

        bundle = compare_poses(action_id, ref_normalized, selected_normalized, self.registry, use_mirror, focus=focus)

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
            baseline_score = composite_score(baseline.diagnosis)
            current_score = composite_score(bundle.diagnosis)
            percentage = (baseline_score - current_score) / max(baseline_score, 1e-6) * 100.0
            improved = bundle.diagnosis.status == "aligned" or percentage > 5.0
            improvement = Improvement(
                baseline_analysis_id=baseline_analysis_id,
                current_analysis_id=analysis_id,
                improved=improved,
                improvement_percent=round(percentage, 1),
                message=(
                    ("这次已经没有明显主导偏差，可以把完整动作加回来。" if bundle.diagnosis.status == "aligned" else f"这次关键偏差降低约 {percentage:.0f}% ，可以把完整动作加回来。")
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
            created_at=datetime.now(timezone.utc),
            duration_seconds=candidate_sequence.duration_seconds,
            pose_coverage=candidate_sequence.coverage,
            mirrored_input=use_mirror,
            trigger_source="feed_pause",
            diagnosis=bundle.diagnosis,
            comparison_image_url=comparison_url,
            improvement=improvement,
            warnings=warnings,
        )
        self.store.save(result)
        return result

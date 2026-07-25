from __future__ import annotations

import json
import math
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from ..config import Settings
from ..file_lock import catalog_transaction
from ..schemas import AnalysisResult, FocusKind, Improvement, PauseInsight
from .action_matcher import assess_action_match
from .diagnosis import ActionRegistry, calculate_improvement, compare_poses
from .doubao import DoubaoService
from .dtw import dynamic_time_warping
from .features import NormalizedPose, normalize_pose, pose_feature_matrix
from .pause_coach import PauseCoach
from .pose import PoseSequence, extract_pose_sequence, mirror_sequence
from .render import create_comparison_image, create_comparison_video
from .storage import ResultStore
from .teaching_plans import (
    QwenTeachingPlanGenerator,
    TeachingPlanService,
    TeachingPlanSource,
    TeachingPlanStore,
    build_teaching_plan_source,
)
from .video import probe_video


class ReferenceNotReadyError(RuntimeError):
    pass


class ActionMismatchError(ValueError):
    pass


class Analyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = ActionRegistry(settings.action_registry_path)
        self.teaching_plans = TeachingPlanService(
            TeachingPlanStore(settings.teaching_plans_dir),
            QwenTeachingPlanGenerator(settings),
        )
        self.pause_coach = PauseCoach(
            self.registry,
            settings.feed_dir,
            settings.pause_contexts_dir,
            teaching_plans=self.teaching_plans,
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

    @staticmethod
    def identity_references(
        *,
        expected_action_id: str,
        pause_context: NormalizedPose,
        registered_references: dict[str, NormalizedPose],
    ) -> dict[str, NormalizedPose]:
        """Use the selected Feed moment as truth, while retaining other dances as negatives."""

        references = dict(registered_references)
        references[expected_action_id] = pause_context
        return references

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
        pose, _ = self.register_reference_for_teaching(action_id, video_path)
        return pose

    def register_reference_for_teaching(
        self,
        action_id: str,
        video_path: Path,
        source_start_seconds: float | None = None,
    ) -> tuple[PoseSequence, TeachingPlanSource | None]:
        if source_start_seconds is not None:
            if not math.isfinite(source_start_seconds):
                raise ValueError("参考片段在 Feed 中的起始时间必须是有限数字")
            if source_start_seconds < 0:
                raise ValueError("参考片段在 Feed 中的起始时间不能为负数")
            source_duration = probe_video(video_path).duration_seconds
            feed_duration = probe_video(self.pause_coach.feed_path(action_id)).duration_seconds
            if source_start_seconds + source_duration > feed_duration + 0.05:
                raise ValueError("参考片段时间范围必须位于 Feed 视频时长内")
        with catalog_transaction(self.settings.data_dir):
            pose = self._register_reference(action_id, video_path)
            if source_start_seconds is None:
                return pose, None
            reference_video, _ = self.reference_paths(action_id)
            action = self.registry.get(action_id)
            guides = action.get("pause_guides", [])
            default_focus = str(guides[0].get("suggested_focus", "auto")) if guides else "auto"
            if default_focus not in {
                "auto",
                "hands",
                "arms",
                "torso",
                "lower",
                "timing",
                "upper",
            }:
                default_focus = "auto"
            source = build_teaching_plan_source(
                action_id=action_id,
                action_name=action["name"],
                reference_video=reference_video,
                pose=pose,
                source_start_seconds=source_start_seconds,
                default_focus=cast(FocusKind, default_focus),
            )
            if self.registry.path.resolve() != self.settings.built_in_action_registry_path.resolve():
                self.registry.replace_action(
                    {
                        **self.registry.raw(action_id),
                        "teaching_source_hash": source.source_hash,
                    }
                )
            return pose, source

    def _register_reference(self, action_id: str, video_path: Path) -> PoseSequence:
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

            available_actions = [
                item for item in self.registry.list() if self.reference_ready(item["id"])
            ]
            registered_references = {
                item["id"]: normalize_pose(PoseSequence.load(self.reference_paths(item["id"])[1]))
                for item in available_actions
            }
            identity_references = self.identity_references(
                expected_action_id=action_id,
                pause_context=ref_normalized,
                registered_references=registered_references,
            )
            match = assess_action_match(
                expected_action_id=action_id,
                candidate_variants=[normal, mirrored_normalized],
                references=identity_references,
                action_names={item["id"]: item["name"] for item in available_actions},
                maximum_match_cost=self.settings.action_match_max_cost,
                alternative_ratio=self.settings.action_match_alternative_ratio,
            )
            if not match.matched:
                raise ActionMismatchError(match.message)

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
            comparison_video_path = self.settings.comparison_videos_dir / f"{analysis_id}.mp4"
            rendered_video = create_comparison_video(
                reference_pose=reference_sequence,
                candidate_pose=selected_sequence,
                alignment_path=bundle.dtw.path,
                highlight=bundle.diagnosis.body_part,
                output_path=comparison_video_path,
            )
        comparison_url = f"/media/visualizations/{rendered.name}" if rendered else None
        comparison_video_url = (
            f"/media/comparison-videos/{rendered_video.name}" if rendered_video else None
        )
        if bundle.diagnosis.status == "issue_detected":
            refinement = await self.doubao.refine_feedback(
                bundle.diagnosis, action["name"], rendered
            )
            if refinement.overall:
                bundle.diagnosis.overall_feedback = refinement.overall
            if refinement.focus:
                bundle.diagnosis.vlm_summary = refinement.focus

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
                        "这遍顺了！刚才那个卡壳点基本消失，可以把完整动作接回来。"
                        if bundle.diagnosis.status == "aligned"
                        else f"刚才那个卡壳点顺了约 {percentage:.0f}%！方向对了，继续保持。"
                    )
                    if improved
                    else "还差一点，先别加难度。只练刚才那一小段，再来一遍。"
                ),
            )

        warnings: list[str] = []
        if use_mirror:
            warnings.append("你拍的是镜像画面，AI 已自动把左右翻回来，不用你烧脑。")
        if candidate_sequence.coverage < 0.8:
            warnings.append("有几帧没看清动作，可能是光线、遮挡或没拍到全身。灯开亮一点，全身别出框。")

        result = AnalysisResult(
            id=analysis_id,
            session_id=session_id,
            action_id=action_id,
            created_at=datetime.now(UTC),
            duration_seconds=candidate_sequence.duration_seconds,
            analyzed_frame_count=len(candidate_sequence.landmarks),
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
            comparison_video_url=comparison_video_url,
            improvement=improvement,
            warnings=warnings,
        )
        self.store.save(result)
        return result

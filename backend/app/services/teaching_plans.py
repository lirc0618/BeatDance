from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from ..schemas import FocusKind, TeachingPlan, TeachingSegment
from .pose import PoseSequence

ACTION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class TeachingPlanSource:
    action_id: str
    action_name: str
    reference_video: Path
    pose: PoseSequence
    source_hash: str
    source_start_seconds: float
    source_end_seconds: float
    default_focus: FocusKind = "auto"


class TeachingPlanGenerator(Protocol):
    @property
    def configured(self) -> bool: ...

    def generate(self, source: TeachingPlanSource) -> TeachingPlan: ...


class TeachingPlanStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def path(self, action_id: str) -> Path:
        if not ACTION_ID.fullmatch(action_id):
            raise ValueError("教学计划动作 ID 无效")
        return self.directory / f"{action_id}.json"

    def load(self, action_id: str) -> TeachingPlan | None:
        path = self.path(action_id)
        if not path.is_file():
            return None
        try:
            return TeachingPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def save(self, plan: TeachingPlan) -> None:
        target = self.path(plan.action_id)
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending")
        try:
            pending.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)


class TeachingPlanService:
    def __init__(self, store: TeachingPlanStore, generator: TeachingPlanGenerator):
        self.store = store
        self.generator = generator

    def prepare(self, source: TeachingPlanSource) -> TeachingPlan | None:
        current = self.store.load(source.action_id)
        if current and current.source_hash == source.source_hash:
            return current
        if not self.generator.configured:
            return None
        plan = self.generator.generate(source)
        self.store.save(plan)
        return plan

    def segment_for(
        self,
        action_id: str,
        timestamp_seconds: float,
        *,
        expected_source_hash: str | None = None,
    ) -> TeachingSegment | None:
        plan = self.store.load(action_id)
        if not plan:
            return None
        if expected_source_hash and plan.source_hash != expected_source_hash:
            return None
        return next(
            (
                segment
                for segment in plan.segments
                if segment.start_seconds <= timestamp_seconds <= segment.end_seconds
            ),
            None,
        )

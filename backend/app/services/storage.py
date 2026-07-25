from __future__ import annotations

from pathlib import Path

from ..schemas import AnalysisResult


class ResultStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def save(self, result: AnalysisResult) -> None:
        (self.directory / f"{result.id}.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

    def load(self, analysis_id: str) -> AnalysisResult:
        path = self.directory / f"{analysis_id}.json"
        if not path.exists():
            raise FileNotFoundError(analysis_id)
        return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, analysis_id: str) -> None:
        (self.directory / f"{analysis_id}.json").unlink(missing_ok=True)

import subprocess
from pathlib import Path


def test_strict_content_check_accepts_the_project_permission_record() -> None:
    root = Path(__file__).parents[2]

    result = subprocess.run(
        [
            str(root / ".venv" / "bin" / "python"),
            str(root / "scripts" / "validate_content_matrix.py"),
            "--strict-sources",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout
    assert "20 条内容" in result.stdout
    assert "原始来源链接待补" in result.stdout

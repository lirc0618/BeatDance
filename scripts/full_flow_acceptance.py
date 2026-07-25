#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from http_client import build_http_client

SAMPLES = {
    "groove_step": "breakdance_6_step.mp4",
    "arm_wave": "arm_movements_reference.mp4",
    "cross_step": "tendu_reference.mp4",
    "two_step_demo": "simple_step.mp4",
}
FEED_DURATIONS = {
    "groove_step": 20.8,
    "arm_wave": 28.4,
    "cross_step": 14.76,
    "two_step_demo": 17.44,
}
CREATED_ANALYSIS_IDS: list[str] = []


def create_blank_video(path: Path, duration: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("完整流程验收需要 ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x240:r=15:d={duration}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def create_mirrored_video(source: Path, target: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("完整流程验收需要 ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "8",
            "-t",
            "4",
            "-i",
            str(source),
            "-an",
            "-vf",
            "hflip",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
    )


def post_video(client, url: str, video: Path, data: dict[str, str]):
    with video.open("rb") as handle:
        response = client.post(
            url,
            data=data,
            files={"video": (video.name, handle, "video/mp4")},
        )
    if response.is_success and url.endswith("/analyze"):
        analysis_id = response.json().get("id")
        if analysis_id:
            CREATED_ANALYSIS_IDS.append(str(analysis_id))
    return response


def cleanup_created_results(api: str, *, strict: bool = False) -> None:
    if not CREATED_ANALYSIS_IDS:
        return
    failures: list[str] = []
    try:
        with build_http_client(timeout=10, api_url=api) as client:
            for analysis_id in set(CREATED_ANALYSIS_IDS):
                response = client.delete(f"{api}/results/{analysis_id}")
                if response.status_code not in (200, 404):
                    failures.append(f"{analysis_id}: HTTP {response.status_code}")
    except Exception as exc:
        failures.append(str(exc))

    if failures:
        message = "验收结果清理失败：" + "; ".join(failures)
        if strict:
            raise RuntimeError(message)
        print(f"WARNING: {message}", file=sys.stderr)
        return
    CREATED_ANALYSIS_IDS.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="通过真实 HTTP API 验收对拍完整本地流程")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--admin-token", default="change-me")
    parser.add_argument("--runs-per-action", type=int, default=5)
    args = parser.parse_args()
    api = args.api.rstrip("/")
    parsed_api = urlsplit(api)
    public_origin = f"{parsed_api.scheme}://{parsed_api.netloc}"
    atexit.register(cleanup_created_results, api)
    project_root = Path(__file__).resolve().parents[1]
    samples_dir = project_root / "assets" / "samples" / "open_sources"

    with build_http_client(timeout=180, api_url=api) as client, tempfile.TemporaryDirectory() as temp_dir:
        health = client.get(f"{api}/health")
        health.raise_for_status()
        health_data = health.json()
        assert health_data["status"] == "ok"
        assert health_data["total_actions"] >= 4, health_data
        assert (
            health_data["reference_actions_ready"] == health_data["total_actions"]
        ), health_data
        doubao_configured = health_data["doubao_configured"]

        actions = client.get(f"{api}/actions")
        actions.raise_for_status()
        action_data = actions.json()
        assert len(action_data) >= 4
        assert all(action["reference_ready"] for action in action_data)
        assert all(action["feed_video_url"].startswith("/media/feed/") for action in action_data)

        invalid_pause = client.post(
            f"{api}/actions/groove_step/pause-insight",
            json={"timestamp_seconds": 1000.0},
        )
        assert invalid_pause.status_code == 422
        assert "暂停时间点" in invalid_pause.json()["detail"]

        pause_insights = {}
        for action_id, duration in FEED_DURATIONS.items():
            paused_at = duration / 2
            response = client.post(
                f"{api}/actions/{action_id}/pause-insight",
                json={
                    "timestamp_seconds": paused_at,
                },
            )
            response.raise_for_status()
            insight = response.json()
            assert insight["timestamp_seconds"] == round(paused_at, 2)
            assert insight["feed_duration_seconds"] == duration
            assert insight["sampled_frame_count"] > 0
            assert insight["context_start_seconds"] < paused_at
            assert insight["context_end_seconds"] > paused_at
            assert len(insight["search_results"]) == 3
            assert len({item["view_type"] for item in insight["search_results"]}) == 3
            pause_insights[action_id] = insight

        short_video = Path(temp_dir) / "short.mp4"
        long_video = Path(temp_dir) / "long.mp4"
        blank_video = Path(temp_dir) / "blank.mp4"
        mirrored_video = Path(temp_dir) / "mirrored.mp4"
        create_blank_video(short_video, 2)
        create_blank_video(long_video, 9)
        create_blank_video(blank_video, 4)
        create_mirrored_video(samples_dir / "爱你.MP4", mirrored_video)

        for video in (short_video, long_video):
            response = post_video(
                client,
                f"{api}/analyze",
                video,
                {"action_id": "groove_step", "session_id": "acceptance-invalid"},
            )
            assert response.status_code == 422, response.text
            assert "视频时长需在 3–8 秒之间" in response.json()["detail"]

        response = post_video(
            client,
            f"{api}/analyze",
            blank_video,
            {"action_id": "groove_step", "session_id": "acceptance-invalid"},
        )
        assert response.status_code == 422, response.text
        assert "单人全身入镜" in response.json()["detail"]

        response = post_video(
            client,
            f"{api}/actions/groove_step/reference",
            blank_video,
            {},
        )
        assert response.status_code == 401

        with blank_video.open("rb") as handle:
            response = client.post(
                f"{api}/actions/groove_step/reference",
                files={"video": (blank_video.name, handle, "video/mp4")},
                headers={"X-Admin-Token": args.admin_token},
            )
        assert response.status_code == 422, response.text
        health_after_rejected_reference = client.get(f"{api}/health")
        health_after_rejected_reference.raise_for_status()
        health_after_rejection = health_after_rejected_reference.json()
        assert (
            health_after_rejection["reference_actions_ready"]
            == health_after_rejection["total_actions"]
        )

        first_results = {}
        timings: dict[str, list[float]] = {action_id: [] for action_id in SAMPLES}
        signatures: dict[str, set[tuple[str, str, str]]] = {action_id: set() for action_id in SAMPLES}
        for action_id, filename in SAMPLES.items():
            started = time.perf_counter()
            response = post_video(
                client,
                f"{api}/analyze",
                samples_dir / filename,
                {
                    "action_id": action_id,
                    "session_id": f"acceptance-{action_id}",
                    "pause_timestamp_seconds": str(
                        pause_insights[action_id]["timestamp_seconds"]
                    ),
                },
            )
            timings[action_id].append(time.perf_counter() - started)
            response.raise_for_status()
            result = response.json()
            assert result["action_id"] == action_id
            assert result["pose_coverage"] >= 0.8
            assert len(result["diagnosis"]["metrics"]) == 3
            assert len(result["diagnosis"]["search_results"]) == 3
            assert len({item["view_type"] for item in result["diagnosis"]["search_results"]}) == 3
            assert result["comparison_image_url"]
            assert result["source_timestamp_seconds"] == pause_insights[action_id][
                "timestamp_seconds"
            ]
            assert result["source_phase"] == pause_insights[action_id]["phase"]
            assert result["reference_source"] == "feed_pause_context"
            image = client.get(f"{public_origin}{result['comparison_image_url']}")
            image.raise_for_status()
            assert image.headers["content-type"] == "image/jpeg"
            first_results[action_id] = result
            diagnosis = result["diagnosis"]
            signatures[action_id].add(
                (diagnosis["status"], diagnosis["primary_metric"], diagnosis["body_part"])
            )

        for action_id, filename in SAMPLES.items():
            for index in range(1, args.runs_per_action):
                started = time.perf_counter()
                response = post_video(
                    client,
                    f"{api}/analyze",
                    samples_dir / filename,
                    {
                        "action_id": action_id,
                        "session_id": f"acceptance-stability-{index}",
                        "pause_timestamp_seconds": str(
                            pause_insights[action_id]["timestamp_seconds"]
                        ),
                    },
                )
                timings[action_id].append(time.perf_counter() - started)
                response.raise_for_status()
                diagnosis = response.json()["diagnosis"]
                signatures[action_id].add(
                    (diagnosis["status"], diagnosis["primary_metric"], diagnosis["body_part"])
                )

        for action_id in SAMPLES:
            assert len(signatures[action_id]) == 1, (action_id, signatures[action_id])
            assert max(timings[action_id]) <= 25, (action_id, timings[action_id])

        response = post_video(
            client,
            f"{api}/analyze",
            samples_dir / SAMPLES["arm_wave"],
            {"action_id": "groove_step", "session_id": "acceptance-improvement"},
        )
        response.raise_for_status()
        baseline = response.json()
        assert baseline["diagnosis"]["status"] == "issue_detected"
        if not doubao_configured:
            assert baseline["diagnosis"]["vlm_summary"] is None

        response = post_video(
            client,
            f"{api}/analyze",
            samples_dir / SAMPLES["groove_step"],
            {
                "action_id": "groove_step",
                "session_id": "acceptance-improvement",
                "baseline_analysis_id": baseline["id"],
            },
        )
        response.raise_for_status()
        retry = response.json()
        assert retry["improvement"] is not None
        assert retry["improvement"]["baseline_analysis_id"] == baseline["id"]
        assert retry["improvement"]["improved"] is True
        assert retry["improvement"]["improvement_percent"] > 5

        saved = client.get(f"{api}/results/{retry['id']}")
        saved.raise_for_status()
        assert saved.json()["id"] == retry["id"]

        deleted = client.delete(f"{api}/results/{retry['id']}")
        deleted.raise_for_status()
        assert deleted.json() == {"ok": True}
        assert client.get(f"{api}/results/{retry['id']}").status_code == 404
        deleted_image = client.get(f"{public_origin}{retry['comparison_image_url']}")
        assert deleted_image.status_code == 404

        response = post_video(
            client,
            f"{api}/analyze",
            mirrored_video,
            {"action_id": "groove_step", "session_id": "acceptance-mirror"},
        )
        response.raise_for_status()
        mirrored = response.json()
        assert mirrored["mirrored_input"] is True, mirrored
        assert any("镜像" in warning for warning in mirrored["warnings"])

    cleanup_created_results(api, strict=True)
    print("PASS: 四个内置 Feed 动作均已配置参考视频")
    print("PASS: 四条内置 Feed 均可按暂停时刻返回上下文和三种拆解")
    print("PASS: 时长和无人画面校验返回可读错误")
    print("PASS: 非法参考上传被拒绝且不破坏已有参考")
    print("PASS: 四个内置动作均返回诊断、三种拆法和对比图")
    if doubao_configured:
        print("PASS: 豆包已配置时诊断主链正常")
    else:
        print("PASS: 豆包未配置时规则诊断正常降级")
    print("PASS: 错误首练到正确二练的改善、读取与删除闭环")
    print("PASS: 镜像画面自动校正并返回提示")
    for action_id, values in timings.items():
        print(
            f"PASS: {action_id} 连续 {len(values)} 次结果稳定，"
            f"平均 {sum(values) / len(values):.2f}s，最慢 {max(values):.2f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

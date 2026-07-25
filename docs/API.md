# API v0.2

Base URL：`/api/v1`

## GET /actions

每个动作同时代表一个受控 Feed 片段：

```json
{
  "id": "arm_wave",
  "name": "手臂路线·越顶与落位",
  "feed_caption": "手臂越过头顶时，肘和手腕到底沿哪条路线走？",
  "creator": "@Fabiola Mastache · CC BY-SA 4.0",
  "segment_label": "12 秒手臂片段 · 任意暂停",
  "entry_copy": "定格看手怎么走",
  "feed_video_url": "/media/feed/arm_movements_veil.mp4",
  "reference_video_url": "/media/references/arm_wave.mp4",
  "reference_ready": true,
  "tutorial_count": 5
}
```

## POST /actions/{action_id}/pause-insight

JSON 请求：

```json
{"timestamp_seconds": 18.0}
```

服务端读取 Feed 的真实时长与暂停点前后 1.5 秒画面，返回动作阶段、实际画面
运动观察、采样帧数、可能难点，以及按“背面跟练、慢速分拍、局部特写”排列
的三种搜索结果。

## POST /actions/import

使用管理员令牌导入新 Feed，或用同一个 `action_id` 替换已有 Feed。

`multipart/form-data`：

- `video`：至少 3 秒、默认最长 10 分钟且不超过 200 MB；
- `action_id`：小写字母开头，可含数字、下划线或连字符；
- `name`：动作显示名称；
- `pause_at_seconds`：可选，用于抽取清晰参考片段；默认视频中点；
- `description`、`feed_caption`、`creator`：可选文案；
- `focus`：`auto | upper | lower | timing`；
- Header `X-Admin-Token`：管理员令牌。

系统自动转码、抽取参考、提取骨架并原子更新动作清单。响应中的 `created=true`
表示新增，`false` 表示替换。成功后 `/actions` 立即更新，H5 和打开中的小程序
会在约 5 秒内同步，无需重启。

默认最多 50 个动作、Feed 与参考素材合计 5 GB，且同一时刻只转码一个导入
任务；这些限制可通过环境变量调整。同 ID 替换会保留当前和上一代素材，启动时
清理中断导入与已失效代际。生产环境若仍使用默认 `ADMIN_TOKEN=change-me`，
写接口会返回 HTTP 503。

## POST /analyze

`multipart/form-data`：

- `video`：3–8 秒用户模仿；
- `action_id`：Feed 片段 ID；
- `session_id`：匿名会话；
- `focus`：`auto | upper | lower | timing`；
- `pause_timestamp_seconds`：Feed 暂停秒数；
- `baseline_analysis_id`：二练时可选。

新增核心响应：

```json
{
  "trigger_source": "feed_pause",
  "source_timestamp_seconds": 18.0,
  "source_feed_duration_seconds": 106.52,
  "source_context_start_seconds": 16.5,
  "source_context_end_seconds": 19.5,
  "source_phase": "动作进入",
  "reference_source": "feed_pause_context",
  "diagnosis": {
    "primary_error": "右臂动作提前",
    "user_focus": "upper",
    "search_query": "手臂路线 右臂 拍点 慢速分拍 背面跟练",
    "search_results": [
      {
        "title": "慢速启动：肩、肘、腕不要一起动",
        "view_type": "慢速分拍",
        "why_matched": "对应当前主要卡点、身体区域一致"
      }
    ]
  }
}
```

其他端点保持：

- `GET /health`
- `POST /actions/{action_id}/reference`
- `GET /results/{analysis_id}`
- `DELETE /results/{analysis_id}`

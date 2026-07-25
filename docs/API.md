# API v0.2

Base URL：`/api/v1`

## GET /actions

每个动作同时代表一个受控 Feed 片段：

```json
{
  "id": "arm_wave",
  "name": "手臂波浪·肩肘腕传递",
  "feed_caption": "不是手甩过去，是一节一节把波浪送过去。",
  "creator": "@动作拆解实验室",
  "segment_label": "00:03–00:07 · 手部卡点",
  "entry_copy": "定格看手怎么走",
  "reference_video_url": "/media/references/arm_wave.mp4",
  "reference_ready": true,
  "tutorial_count": 5
}
```

## POST /analyze

`multipart/form-data`：

- `video`：3–8 秒用户模仿；
- `action_id`：Feed 片段 ID；
- `session_id`：匿名会话；
- `focus`：`auto | upper | lower | timing`；
- `baseline_analysis_id`：二练时可选。

新增核心响应：

```json
{
  "trigger_source": "feed_pause",
  "diagnosis": {
    "primary_error": "右臂动作提前",
    "user_focus": "upper",
    "search_query": "手臂波浪 右臂 拍点 慢速分拍 背面跟练",
    "search_results": [
      {
        "title": "三拍启动：肩、肘、腕不要一起动",
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

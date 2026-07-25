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
  "skill_focus": "手臂关",
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

## GET /actions/{action_id}/related-videos

查询参数：

- `metric`：`timing | trajectory | angle`；
- `body_part`：诊断出的身体部位；
- `limit`：真实视频卡片数量，范围 1–10。

该接口与本地教学矩阵独立。未配置抖音权限时，返回按本次卡点生成的抖音精准
搜索入口；配置 `DOUYIN_ACCESS_TOKEN` 或 `DOUYIN_CLIENT_KEY` /
`DOUYIN_CLIENT_SECRET` 后，使用抖音开放平台视频搜索接口返回真实视频卡片。
外部接口失败会返回 `provider=platform_search`，不影响分析主流程。

## POST /actions/import

使用管理员令牌导入新 Feed，或用同一个 `action_id` 替换已有 Feed。

`multipart/form-data`：

- `video`：至少 3 秒、默认最长 10 分钟且不超过 200 MB；
- `action_id`：小写字母开头，可含数字、下划线或连字符；
- `name`：动作显示名称；
- `pause_at_seconds`：可选，用于抽取清晰参考片段；默认视频中点；
- `description`、`feed_caption`、`creator`：可选文案；
- `focus`：`auto | hands | arms | torso | lower | timing`；`upper` 仅兼容旧客户端；
- Header `X-Admin-Token`：管理员令牌。

系统自动转码、抽取参考、提取骨架并原子更新动作清单。响应中的 `created=true`
表示新增，`false` 表示替换。成功后 `/actions` 立即更新，H5 和打开中的小程序
会在约 5 秒内同步，无需重启。

配置 `DASHSCOPE_API_KEY` 后，响应返回之后会为本次参考片段生成 Qwen 分阶段教学
计划并按素材哈希缓存。该后台任务失败不会改变导入响应或动作可用性；暂停页会继续
使用现有规则引导。Qwen 只处理管理员参考素材，不接收 `/analyze` 的用户视频。

## GET /sample-library

返回仓库内置的开放许可舞蹈素材，包括预览地址、许可、来源、是否已下载以及
是否已加入首页。H5 的「拓展舞库」使用此接口。

## POST /sample-library/{sample_id}/import

无需从浏览器重新上传服务器已有文件，一键完成 Feed 转码、参考片段、骨架提取
和动作注册。需要 Header `X-Admin-Token`。素材视频可通过
`GET /sample-library/{sample_id}/video` 预览。

默认最多 50 个动作、Feed 与参考素材合计 5 GB，且同一时刻只转码一个导入
任务；这些限制可通过环境变量调整。同 ID 替换会保留当前和上一代素材，启动时
清理中断导入与已失效代际。生产环境必须显式配置至少 24 字符的随机
`ADMIN_TOKEN`；空值、默认值和文档占位值都会让写接口返回 HTTP 503。

## POST /analyze

`multipart/form-data`：

- `video`：3–8 秒用户模仿；
- `action_id`：Feed 片段 ID；
- `session_id`：匿名会话；
- `focus`：`auto | hands | arms | torso | lower | timing`；`upper` 仅兼容旧客户端；
- `pause_timestamp_seconds`：Feed 暂停秒数；
- `baseline_analysis_id`：二练时可选。

服务端在生成诊断前执行动作身份闸门：用户骨架必须与 `action_id` 本次暂停点前后
1.5 秒的动作匹配；其他已注册动作只用于识别明显传错的舞。明显更像其他动作或
与当前暂停片段相差过大时返回 HTTP 422，`detail`
直接说明“更像哪支舞”或“与当前动作对不上”，不会返回伪造的局部纠错。

`hands` 是手势级分析，使用手腕、拇指、食指和小指方向判断掌心与开合；当这些点
不可见时同样返回 HTTP 422，要求把双手拍清楚，不提供逐指关节评分。

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
    "overall_feedback": "整体能跟上动作，但关键部位还有明显偏差。",
    "primary_error": "右臂抢跑了，像偷偷开了倍速",
    "vlm_summary": "重点看右臂：听到重拍再出手，先连做三次。",
    "user_focus": "arms",
    "search_query": "手臂路线 右臂 拍点 慢速分拍 背面跟练",
    "search_results": [
      {
        "title": "慢速启动：肩、肘、腕不要一起动",
        "view_type": "慢速分拍",
        "why_matched": "正好治这个问题、盯的是同一块",
        "source_platform": "douyin_search",
        "source_url": "",
        "license_status": "permission_granted",
        "license_name": "项目已获授权",
        "download_policy": "local_allowed",
        "local_asset": "assets/tutorials/aini-mirror.mp4",
        "url": "/media/tutorials/aini-mirror.mp4"
      }
    ]
  }
}
```

当 `local_asset` 为空时，`url` 也保持目录中配置的外部链接或空字符串；当本地
文件按教学记录 ID 登记后，服务端会自动返回 `/media/tutorials/<id>.mp4`。

其他端点保持：

- `GET /health`
- `POST /actions/{action_id}/reference`
- `GET /results/{analysis_id}`
- `DELETE /results/{analysis_id}`

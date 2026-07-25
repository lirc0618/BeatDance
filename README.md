# 对拍（BeatDance）

对拍（英文名 BeatDance）是面向抖音视觉搜索赛题的可部署 MVP。用户播放 Feed 视频并停在没看懂的一秒，系统记录时间点，由服务端读取真实视频时长和前后动作帧并先解释这一阶段；用户再上传 3–8 秒模仿，系统把暂停点前后 1.5 秒作为本次姿态参考，通过 MediaPipe、镜像校正、骨架归一化和 DTW 分析整段采样帧、定位个人卡点，并按动作与失败状态召回三条专属拆法，支持二次上传验证是否改善。结果同时提供整段匿名骨架回放和关键一帧对比，不保存用户原视频。

## 和整舞 AI 教练的区别

本项目不做整支舞评分、视频存储和练舞统计。核心是：

```text
Feed 暂停 → 卡点诊断 → 动作片段搜索 → 二练验证
```

详见：

- `docs/PRD.md`
- `docs/COMPETITIVE_POSITIONING.md`
- `docs/PROJECT_CONTROL.md`
- `docs/MIGRATION_V1_TO_V2.md`
- `docs/CONTENT_MATRIX.md`

## 本地开发启动

需要 Python 3.11、`uv` 和 FFmpeg。H5 浏览器验收另外需要 Node.js 20+：

```bash
make setup
make test
make dev
```

打开：

- H5：`http://localhost:8000/app/`
- API：`http://localhost:8000/docs`

## 导入或替换任意测试视频

五个内置动作只是首次启动的样例。打开 H5 后点击首页的「拓展舞库」，可以：

- 预览 13 条开放许可舞蹈素材并一键加入首页；
- 上传本机 MP4、MOV 或 WEBM；
- 自动完成转码、暂停参考、MediaPipe 骨架提取与动作注册。

本地演示口令为 `change-me`；线上使用 `.env` 中配置的 `ADMIN_TOKEN`。也可以继续
使用命令行导入：

```bash
.venv/bin/python scripts/import_feed.py ./my-dance.mp4 \
  --id my_dance \
  --name "我的动作" \
  --pause-at 6.5 \
  --creator "素材作者" \
  --focus auto
```

导入命令会自动完成 H.264 转码、持久化 Feed、生成通用暂停引导、截取参考片段、
提取 MediaPipe 骨架并注册到动作清单；无需修改 JSON 或重启服务。同一个
`--id` 再导入会安全替换该动作，其他 ID 会继续追加。`--pause-at` 应选择人物
全身清晰、动作有代表性的秒数；省略时使用视频中点。

默认约束：

- Feed 至少 3 秒、不超过 200 MB；
- 单条最长 10 分钟，默认最多 50 个动作、素材总量 5 GB；
- 同一时刻只处理一个导入任务；替换后保留当前与上一代素材；
- 参考点附近需要单人全身清晰；
- 数据保存在 `data/actions.json`、`data/feeds/` 和 `data/references/`；
- Docker 使用 `/data` 持久卷，容器重启不会丢失已导入动作。

本地 `make dev` 仅在回环地址上允许示例令牌 `change-me`。部署时必须在 `.env`
中设置一个至少 24 字符的随机 `ADMIN_TOKEN`；空值、默认值和文档占位值都会
禁用导入和参考视频更新接口。

## 教学内容矩阵

用于动作分析的 Feed、标准参考和测试片段保存在本地；用于推荐的教学内容保存
标题、标签、封面、原始链接、许可状态及可选本地文件路径。推荐索引为：

```text
动作 × 卡点类型 × 教学视角
```

25 条教学记录位于 `backend/app/data/tutorial_catalog.json`。现有诊断服务继续按
动作、失败指标、身体部位和用户关注点进行排序，并从不同教学视角中返回 Top-3。
这些卡片是由当前 Feed 生成的“AI 即时拆解”，不是外部视频推荐。

暂停解释页和最终诊断页另有「搜外部相关视频」窗口。系统会把动作名、身体部位
和卡点类型组合成精准搜索词：

- 未配置开放平台凭证时，提供抖音精准搜索入口；
- 配置抖音开放平台视频搜索权限后，窗口直接展示真实标题、封面、作者、点赞数
  和原平台链接；
- 外部接口失败时自动退回平台搜索入口，不阻塞动作分析和练习。

H5 会直接打开原平台；微信小程序受外链限制，会打开同样的结果窗口并复制原视频
或搜索结果链接。

抖音官方检索配置放在 `.env`：

```env
DOUYIN_CLIENT_KEY=
DOUYIN_CLIENT_SECRET=
# 调试时也可直接填写短期 token；填写后优先使用
DOUYIN_ACCESS_TOKEN=
```

开发阶段执行结构校验：

```bash
make content-check
```

演示发布前执行严格来源与许可校验：

```bash
.venv/bin/python scripts/validate_content_matrix.py --strict-sources
```

当前 25 条教学视频已记录为 `permission_granted + local_allowed`，实际文件位于
`assets/tutorials/`。每个动作包含镜像、局部、慢速、定格和新手版，均保留 AAC
音轨；H5 与小程序会在推荐卡片中直接播放。需要从五条授权源视频重新生成时执行：

```bash
make tutorial-build
make reference-build
```

## 本地完整流程验收

先在一个终端启动服务：

```bash
make dev
```

再在另一个终端准备开放许可 Feed、截取同源参考并注册：

```bash
make demo-seed
```

执行真实 API 完整闭环和 H5 浏览器测试：

```bash
make setup-h5
make accept
```

验收覆盖五条内置 Feed 的真实暂停时间点、前后上下文、动作阶段解释、时长/无人
画面拒绝、参考更新保护、首练诊断、Top-3 多样化搜索、整段骨架回放与关键帧对比图、豆包未配置
降级、二练改善、镜像校正、结果删除，以及五个动作各连续 5 次的稳定性和
耗时。同源开放样例能验证产品链路，但不能替代真人同机位错误样本标定。

使用仓库自带的开放视频跑通参考注册和分析：

```bash
.venv/bin/python scripts/register_reference.py \
  --api http://localhost:8000/api/v1 \
  --token change-me \
  --action groove_step \
  --video assets/samples/open_sources/breakdance_6_step.mp4

.venv/bin/python scripts/smoke_test.py \
  --action groove_step \
  --video assets/samples/open_sources/breakdance_6_step.mp4
```

## Docker 启动

```bash
cp .env.example .env
docker compose up --build -d
```

爵士参考会随镜像自动初始化。首次启动后，在宿主机运行以下命令，为另外四个
内置动作导入 Feed 并生成诊断参考：

```bash
make demo-seed ADMIN_TOKEN="<与 .env 中相同的 ADMIN_TOKEN>"
```

完成后 `groove_step`、`arm_wave`、`cross_step`、`two_step_demo` 和
`jazz_demo` 五条均应显示为 `reference_ready=true`。

之后可直接从宿主机运行 `scripts/import_feed.py` 向 Docker API 追加或替换
任意动作，文件与动作清单都会写入持久卷。

## 核心 API 变化

`POST /api/v1/analyze` 新增：

- `focus=auto|hands|arms|torso|lower|timing`（`upper` 仅保留旧客户端兼容）
- `pause_timestamp_seconds`（Feed 总时长由服务端读取）

暂停解释：

- `POST /api/v1/actions/{action_id}/pause-insight`

结果新增：

- `diagnosis.overall_feedback`
- `diagnosis.vlm_summary`（重点问题和改法）
- `diagnosis.search_query`
- `diagnosis.search_results`
- `diagnosis.user_focus`
- `reference_source=feed_pause_context`

H5 会在上传前检查 3–8 秒时长、横竖屏比例、画面尺寸和首帧清晰度；时长或文件
大小不合规则阻止提交，尺寸或清晰度不足只给出重拍建议。所有页面的视频共用一个
播放互斥规则，同一时间只会播放一条。

服务端会先把用户骨架与当前动作及其他已注册动作做身份匹配。明显传错舞时返回
HTTP 422，并停止技术纠错，避免把“不属于这支舞”误报成手脚细节问题。关注点分为
手势、手臂、核心/躯干、脚步、节奏和 AI 自动；手势使用 Pose 的手腕及三类指尖点，
用于判断掌心方向和开合，不宣称逐指关节精度。

## 隐私与边界

- 原始用户视频默认分析后删除；
- 动作身份匹配只比较匿名骨架，不做人脸或个人身份识别；
- 五个内置动作是受控验收集；其他视频可以导入，但使用通用阈值，尚未承诺标定准确率；
- 不宣称专业舞蹈评分或医学建议。

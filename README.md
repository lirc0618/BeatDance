# 定格教练 · 卡点搜索

面向抖音视觉搜索赛题的可部署 MVP。用户播放 Feed 视频并停在没看懂的一秒，系统记录时间点，由服务端读取真实视频时长和前后动作帧并先解释这一阶段；用户再上传 3–8 秒模仿，系统把暂停点前后 1.5 秒作为本次姿态参考，通过 MediaPipe、镜像校正、骨架归一化和 DTW 定位个人卡点，按失败状态召回背面、慢速和局部三种拆解方式，支持二次上传验证是否改善。

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

验收覆盖三条长 Feed 的真实暂停时间点、前后上下文、动作阶段解释、时长/无人
画面拒绝、参考更新保护、首练诊断、Top-3 多样化搜索、对比图、豆包未配置
降级、二练改善、镜像校正、结果删除，以及三个动作各连续 5 次的稳定性和
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

注册三个参考片段：

```bash
python scripts/register_reference.py \
  --api http://localhost:8000/api/v1 \
  --token change-me \
  --action arm_wave \
  --video assets/references/arm_wave.mp4
```

依次配置 `arm_wave`、`groove_step`、`cross_step`。

## 核心 API 变化

`POST /api/v1/analyze` 新增：

- `focus=auto|upper|lower|timing`
- `pause_timestamp_seconds`（Feed 总时长由服务端读取）

暂停解释：

- `POST /api/v1/actions/{action_id}/pause-insight`

结果新增：

- `diagnosis.search_query`
- `diagnosis.search_results`
- `diagnosis.user_focus`
- `reference_source=feed_pause_context`

## 隐私与边界

- 原始用户视频默认分析后删除；
- 不做人脸身份识别；
- 当前只支持 3 个受控动作 Feed；
- 不宣称专业舞蹈评分或医学建议。

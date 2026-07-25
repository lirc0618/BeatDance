# 定格教练 · 卡点搜索

面向抖音视觉搜索赛题的可部署 MVP。用户从 Feed 中暂停一个 3–8 秒动作片段，表达自己关注手部、脚步或拍点，再上传模仿。系统通过 MediaPipe、镜像校正、骨架归一化和 DTW 定位一个关键卡点，并按失败状态召回三种不同拆解方式，支持二次上传验证是否改善。

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

## 5 分钟启动

```bash
cp .env.example .env
docker compose up --build -d
```

打开：

- H5：`http://localhost:8000/app/`
- API：`http://localhost:8000/docs`

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

结果新增：

- `diagnosis.search_query`
- `diagnosis.search_results`
- `diagnosis.user_focus`

## 隐私与边界

- 原始用户视频默认分析后删除；
- 不做人脸身份识别；
- 仅支持 3 个受控短动作；
- 不宣称专业舞蹈评分或医学建议。

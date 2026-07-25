# 定格教练 · 卡点搜索 Skill

## 1. Skill 名称

`freeze-frame-search-coach`

## 2. 目标

把短视频 Feed 中被用户暂停的 3–8 秒动作片段，转化为一次“按失败状态搜索教学内容”的闭环：

1. 理解用户关注手部、脚步还是拍点；
2. 将模仿视频与参考片段对齐；
3. 定位节奏、路线、幅度中最关键的一处卡点；
4. 生成状态搜索词；
5. 召回三种不同视角或难度的拆解内容；
6. 二次上传验证是否改善。

## 3. 适用场景

- 用户在 Feed 中暂停一个没看懂的短动作；
- 评论区常见“求背面、求慢放、脚怎么走”的片段；
- 用户愿意上传自己的 3–8 秒模仿；
- 系统需要把“分析”继续承接到内容搜索和练习验证。

MVP 支持：`groove_step`、`arm_wave`、`cross_step`。

## 4. 输入

```json
{
  "action_id": "arm_wave",
  "video": "multipart video file",
  "session_id": "anonymous-session-id",
  "focus": "auto | upper | lower | timing",
  "baseline_analysis_id": "optional-first-analysis-id"
}
```

## 5. 工作流

```text
Feed 暂停片段 + 用户关注意图
  ↓
video.validate
  ↓
pose.extract / normalize / mirror_select
  ↓
motion.align (DTW)
  ↓
motion.diagnose
  - 节奏时差
  - 身体组路线误差
  - 关节幅度误差
  - 只选择一个主要卡点
  ↓
search.query_build
  - 动作 + 身体部位 + 卡点 + 视角需求
  ↓
content.retrieve
  - 卡点匹配
  - 身体区域匹配
  - 用户意图匹配
  - view_type 多样化去重
  ↓
feedback.generate
  - 规则基础反馈
  - 豆包 VLM 可选核验和改写
  ↓
result.verify
  - 二练与首次结果比较
```

## 6. 输出

```json
{
  "primary_error": "右臂动作提前",
  "priority_feedback": "其他部分先别改，把右臂启动稍微延后。",
  "drill": "只练右臂，跟四拍做 3 次。",
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
```

## 7. 满足判断

- 诊断必须产生一个可执行卡点；
- 搜索结果至少两种不同 `view_type`；
- 低质量输入要求重拍；
- 二练综合偏差降低超过 5% 或进入 `aligned`，视为改善；
- 未改善时继续原卡点，不追加多个新问题。

## 8. 边界

- 不做整支舞评分、视频存储和训练统计；
- 不进行身份识别、身体审美或天赋判断；
- 不用于医疗、康复、高风险运动；
- VLM 不负责精确角度和时差计算；
- 本地标签库用于 MVP，未来可替换为抖音内容检索工具。

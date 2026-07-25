# 系统架构 v2

## 总体链路

```mermaid
flowchart LR
    A[受控动作 Feed] --> B[真实暂停事件与准确时间点]
    B --> C[服务端校验时长并读取前后 1.5 秒真实帧]
    C --> C1[动作阶段与画面运动解释]
    C1 --> D0[用户选择关注点并上传模仿]
    D0 --> D[FastAPI 视频校验与抽帧]
    C --> E[暂停上下文 MediaPipe Pose]
    D --> E[用户模仿 MediaPipe Pose]
    E --> F[镜像校正与骨架归一化]
    F --> G[DTW 时序对齐]
    G --> H[节奏 / 路线 / 幅度卡点]
    H --> I[生成状态搜索词]
    I --> J[动作内容标签库 Top-3 检索]
    H --> K[豆包 VLM 反馈核验与改写]
    J --> L[不同视角拆解结果]
    K --> L
    L --> M[用户二练]
    M --> G
```

## 与 v1 的架构差异

v1 在诊断后只返回一个教学项；v2 增加了明确的视觉搜索层：

- 输入索引：动作 ID、主要卡点、身体部位、用户关注点；
- 检索字段：错误类型、身体区域、视角类型、难度和标签；
- 排序：卡点匹配 > 身体部位 > 用户意图 > 内容形式；
- 多样化：优先返回不同 `view_type`，避免三个结果同质；
- 输出：搜索词、匹配原因、Top-3 内容卡。

## 模型分工

- MediaPipe：连续人体关键点；
- OpenCV / FFmpeg：读取真实 Feed 帧并原子生成暂停上下文；
- DTW / 数值规则：计算动作差异；
- 标签检索：决定“该看哪种内容”；
- 豆包 VLM：结合关键帧核验语境，生成一句谨慎反馈；
- 未来抖音检索 Skill：把本地标签检索替换为真实内容召回。

## 部署

```text
HTTPS 域名
└── Docker / FastAPI
    ├── /api/v1/actions
    ├── /api/v1/actions/import
    ├── /api/v1/actions/{id}/pause-insight
    ├── /api/v1/analyze
    ├── /app/                 H5
    ├── /media/feed/          开放许可 Feed 视频
    ├── /media/references/    同源短诊断参考
    ├── /media/visualizations/
    └── /data/
        ├── actions.json       可动态扩展的动作清单
        ├── feeds/             导入的持久化 Feed
        └── references/        不可变参考代际
```

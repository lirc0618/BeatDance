# 教学内容矩阵

## 目标

BeatMatch 将视频资产拆成两类管理：

1. **动作分析资产**：Feed、标准参考、正确/错误/镜像测试片段。需要真实视频文件，放在本地数据目录或对象存储。
2. **教学推荐内容**：标题、动作标签、卡点类型、教学视角、封面、原始链接和许可信息。已获许可的视频可保存本地副本。

推荐层的基本索引是：

```text
动作 × 卡点类型 × 教学视角
```

当前目录包含 4 个动作、每个动作 5 条教学记录，共 20 条。诊断服务仍按 `error_type`、`body_part`、`focus` 和 `view_type` 排序并返回 Top-3，但内容不再写死在 Python 动作画像中。

## 文件位置

```text
backend/app/data/tutorial_catalog.json   教学内容目录
backend/app/services/tutorial_catalog.py 加载、缓存与运行时校验
scripts/validate_content_matrix.py       覆盖度与许可校验
```

## 许可状态

- `unverified`：来源或许可尚未核验。只能作为搜索/占位元数据。
- `verified_open`：已确认开放许可，并记录许可名称与链接。
- `permission_granted`：已获得作者或权利人的明确授权。

下载策略：

- `link_only`：只保存外链和元数据，不把视频提交到仓库。
- `local_allowed`：允许保存本地副本。仅能与 `verified_open` 或 `permission_granted` 搭配；文件已复制到仓库时再填写 `local_asset`。

## 校验

结构校验允许来源待补，用于开发阶段：

```bash
make content-check
```

演示发布前执行严格校验：

```bash
.venv/bin/python scripts/validate_content_matrix.py --strict-sources
```

当前 20 条记录已标记为 `permission_granted + local_allowed`，并由目录顶层的
`permission_record` 记录项目方在 2026-07-25 的统一授权确认。直接授权不要求
伪造公开来源 URL，因此严格校验接受这份记录，但仍提示逐条补充 `source_url`，
便于后续审计与署名。

## 新增内容记录

每条记录至少应回答：

- 属于哪个动作：`action_id`
- 解决哪个卡点：`error_type`
- 主要观察哪个部位：`body_part`
- 从什么视角教学：`view_type`
- 原始来源在哪里：`source_url`
- 是否允许本地保存：`download_policy`
- 许可依据是什么：`license_status`、`license_name`、`license_url`

同一动作建议至少保留三种不同教学视角，例如镜像跟跳、局部特写、慢速分拍、脚步俯拍、定格拆解或新手简化。

本地教学视频建议统一放在 `assets/tutorials/`，并以目录记录的 `id` 命名，例如
`assets/tutorials/aini-mirror.mp4`。复制完成后将该相对路径写入 `local_asset`。
运行时会自动把该路径转换为 `/media/tutorials/aini-mirror.mp4`，H5 和小程序
无需再手工拼接媒体地址。

当前 20 条记录均已生成本地有声视频。执行 `make tutorial-build` 可以从四条
授权演示视频重新生成镜像、局部、慢速、定格和新手版。

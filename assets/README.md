# 视频资产准备

请创建：

```text
assets/
  references/
    jazz_demo.current.json
    jazz_demo-<generation>.mp4
    jazz_demo-<generation>.npz
  errors/
    groove_step_timing_01.mp4
    groove_step_timing_02.mp4
    groove_step_trajectory_01.mp4
    ...
  tutorials/
    ...
```

`assets/references/` 保存随项目发布的爵士参考；另外四个内置动作通过
`make demo-seed` 生成运行时参考，写入 `data/references/`。导入的新动作也使用
同一运行时目录。

统一要求：

- 1080p 或 720p；
- 3–8 秒；
- 15 FPS 以上；
- 正面固定机位；
- 人物全身占画面高度约 65%–85%；
- 纯色或不杂乱背景；
- 标准与错误视频由同一人、同一机位优先；
- 明确只改变一种错误，避免错误标签相互污染。

## 先用开放样例跑通管线

```bash
python scripts/download_open_samples.py
```

下载后的 13 条 Creative Commons 视频位于 `assets/samples/open_sources/`，覆盖
breakdance、站立踏步、手臂路线、恰恰、芭蕾、爵士和踢踏舞，可用于上传、
解码、关键点提取和 DTW 烟雾测试。由于人员、机位和动作不同，不能拿它们
训练或标定节奏/轨迹/幅度三类错误。每条素材的作者、来源和许可见同目录
`ATTRIBUTION.md`。

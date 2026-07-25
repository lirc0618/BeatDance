# 开放动作样例

项目已打包一条真实动作样例：

- `breakdance_6_step.gif`：Wikimedia Commons 原始动画；
- `breakdance_6_step.mp4`：由该动画转码得到的 4 秒 H.264 测试视频。

运行实际视频链路烟雾测试：

```bash
PYTHONPATH=backend python scripts/video_sample_smoke_test.py
```

该测试验证真实文件的解码、3–8 秒时长校验、随机帧读取和 FFmpeg 归一化。完整姿态提取必须在项目的 Python 3.11 Docker 环境中运行，因为 MediaPipe 没有 Python 3.13 官方轮子。

另外可在联网环境运行：

```bash
python scripts/download_open_samples.py
```

下载更多开放许可样例。开放样例只能验证工程链路，不能替代同一人、同一机位录制的标准/错误样本标定。

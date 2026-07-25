# 真实动作视频测试报告

测试日期：2026-07-25

## 测试素材

- 文件：`assets/samples/open_sources/breakdance_6_step.mp4`
- 来源：Wikimedia Commons 动画 `6-step example.gif`
- 内容：breakdance 六步动作
- 规格：H.264、640×360、15 FPS、60 帧、4.0 秒

许可证与修改说明见 `assets/samples/open_sources/ATTRIBUTION.md`。

## 已实际执行并通过

1. OpenCV 成功打开并读取视频；
2. 时长为 4.0 秒，通过项目 3–8 秒限制；
3. 成功跳转并读取第 2 秒画面，尺寸为 360×640×3；
4. FFmpeg 成功重新归一化为 H.264/yuv420p；
5. 归一化后仍为 4.0 秒、15 FPS、60 帧；
6. 后端 DTW、角度、轨迹、节奏、内容召回等 8 项单元测试全部通过。

复现命令：

```bash
PYTHONPATH=backend python scripts/video_sample_smoke_test.py
pytest -q backend/tests
```

## 尚未完成的测试

当前执行环境是 Python 3.13，MediaPipe 官方包没有对应轮子，因此本环境无法完成：

```text
真实视频 → MediaPipe 33 点 → 骨架归一化 → DTW → 卡点诊断
```

项目 Dockerfile 已固定 Python 3.11，可在团队服务器执行完整链路。完成标准是：

1. 容器成功安装 MediaPipe；
2. 该样例可提取姿态且输出覆盖率；
3. 注册为参考动作后，同文件分析应判定为 `aligned`；
4. 对人工制造的节奏变体应输出 timing 类型偏差；
5. 最终仍需团队真人同机位样本完成阈值标定。

## 修正后的结论

此前“已有视频”的表述不准确：旧压缩包只有下载脚本和素材清单，没有实际视频二进制。本轮已经补入一条真实开放素材并完成可执行测试。项目当前不再把“有下载器”等同于“已完成视频端到端验证”。

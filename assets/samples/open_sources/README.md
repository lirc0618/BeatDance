# 开放动作样例

项目已打包用于上传诊断和 Feed 暂停测试的开放动作样例：

- `breakdance_6_step.gif`：Wikimedia Commons 原始动画；
- `breakdance_6_step.mp4`：由该动画转码得到的 4 秒 H.264 测试视频。
- `breakdance_2_step.mp4`：6.1 秒 breakdance 两步示范；
- `simple_step.mp4`：3.8 秒简单踏步。
- `six_step_tutorial.mp4`：106.5 秒六步完整教程；
- `arm_movements_veil.mp4`：12 秒手臂路线片段；
- `tendu_tutorial.mp4`：16.3 秒 Tendu 单人教程；
- `ballet_assemble.mp4`：单人起跳与并腿落地；
- `ballet_balance.mp4`：单人左右重心切换；
- `ballet_chasse.mp4`：单人横向并步；
- `ballet_plie.mp4`：单人膝髋下沉与回正；
- `jazz_pas_de_bourree.mp4`：单人爵士交叉步；
- `tap_dance_technique.mp4`：单人踢踏舞脚步教程；
- `爵士.MP4`：项目方提供并确认可用于本项目保存与演示的爵士 Feed；
- `arm_movements_reference.mp4`、`tendu_reference.mp4`：从对应 Feed 截取的
  5 秒同源诊断参考。

运行实际视频链路烟雾测试：

```bash
make video-smoke
```

该测试验证真实文件的解码、3–8 秒时长校验、随机帧读取和 FFmpeg 归一化。
完整本地流程使用 Python 3.11 环境，已覆盖 MediaPipe 姿态提取、DTW、诊断、
搜索召回和二练验证。

另外可在联网环境运行：

```bash
python scripts/download_open_samples.py
```

下载更多开放许可样例。开放样例只能验证工程链路，不能替代同一人、同一机位录制的标准/错误样本标定。

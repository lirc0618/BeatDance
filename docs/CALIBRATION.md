# 0. 开放样例预检

在录制真人标定集前，可以先运行：

```bash
python scripts/download_open_samples.py
```

用生成的三个 MP4 检查服务能否正常完成视频解码、MediaPipe 提取和基础结果返回。开放样例不能用于阈值标定，因为标准与错误视频必须尽量由同一人、同一机位拍摄。

## 0.5 动作身份闸门

技术纠错前会把当前暂停点前后 1.5 秒作为目标参考，再用其他已注册动作识别明显
传错的舞。仓库内五个参考动作互相比对的
DTW 归一化距离约为 `1.40–2.26`，四条明确不对应的测试视频约为 `1.28–3.18`，
早期黑客松阈值 `1.15 / 0.72` 会把仍然最像所选动作、但完成度不高的普通模仿
直接拒绝，导致用户无法进入技术纠错。当前默认优先降低误拒率，使用：

- `ACTION_MATCH_MAX_COST=2.0`
- `ACTION_MATCH_ALTERNATIVE_RATIO=0.65`

这只是演示阈值，不是生产准确率结论。所选动作在宽松成本内即可继续纠错；只有另一
已注册动作明显更近时才提示“更像某动作”，差距极大的未知动作仍会拒绝。后续每个
动作至少补 10 条“同舞但水平不同”的真人样本和 10 条“其他舞蹈”样本，再基于误拒率
继续标定，避免乱猜舞名。

# 诊断标定操作手册

当前代码链路已经可运行，但能否稳定识别 9 类预设错误，取决于真人样本标定。该步骤是下一阶段的最高优先级。

## 1. 录制数据

先生成清单：

```bash
python scripts/prepare_dataset.py --samples 2
```

每个动作录制：

- `aligned`：标准动作或足够接近的正常样本；
- `timing`：只制造明显提前/延后，尽量保持轨迹和幅度正确；
- `trajectory`：只改变移动路线，尽量保持节奏和幅度；
- `angle`：只改变展开幅度，尽量保持节奏和路线。

每类至少 2 条，共 24 条评估视频。参考视频另放在 `assets/references/`。

## 2. 注册三个参考动作

```bash
python scripts/register_reference.py --api https://域名/api/v1 --token 管理令牌 --action groove_step --video assets/references/groove_step.mp4
python scripts/register_reference.py --api https://域名/api/v1 --token 管理令牌 --action arm_wave --video assets/references/arm_wave.mp4
python scripts/register_reference.py --api https://域名/api/v1 --token 管理令牌 --action cross_step --video assets/references/cross_step.mp4
```

## 3. 批量评估

```bash
python scripts/evaluate_dataset.py --api https://域名/api/v1 --dir assets/evaluation --output evaluation.csv
```

报告包含实际类别、三项归一化指标、身体部位、置信度和混淆情况。

## 4. 搜索权重

```bash
python scripts/calibrate_diagnosis.py evaluation.csv --output diagnosis-calibration.json
```

将每个动作得到的 `weights` 和 `aligned_threshold` 填回 `backend/app/data/actions.json` 对应动作的 `diagnosis` 字段，重启服务后再次评估。

## 5. 通过标准

- 四类（正常、节奏、轨迹、幅度）总体 Top-1 ≥ 80%；
- 同一视频连续运行 4 次，主类型一致；
- `aligned` 样本不能被强行挑错；
- 节奏错误的方向（提前/延后）符合人工观察；
- 错误身体部位至少在演示样本上稳定。

不要为了追求总体准确率无限调参。最终只需要保证 3 个动作、每个动作 3 类演示错误稳定。

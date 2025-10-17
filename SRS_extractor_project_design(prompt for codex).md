# SRS Extractor 统一打包与项目设计说明

## 一、问题本质与现状总结

你目前的两个脚本（`fast_scan_extract.py` 与 `real_time_extract.py`）在核心算法上类似，区别主要有两点：

| 模块 | 差异点 | 说明 |
|------|----------|------|
| **时间序列光谱提取** | `payload` 偏移不同 | `fast_scan` 从 `block[80:]`；`real_time` 从 `block[84:]`。这导致解出的光谱向量首尾位置不同，需区分。 |
| **背景提取逻辑** | 检测方式不同 | `fast_scan` 使用 marker-based 背景识别 + fallback 间隔扫描；`real_time` 删除 marker 逻辑，仅使用间隔扫描。 |

除此之外：
- 文件头结构尚不明确，**目前无法自动判断文件类型（rapid vs realtime）**；
- 因此，**最安全方案** 是让用户在运行时显式指定模式；
- 同时可在未来版本中引入自动识别逻辑（例如检测特征字节分布或帧间距模式）。

---

## 二、改进后的设计方案

### 🎯 目标
1. 用户手动指定 `--mode` 参数（`fast` 或 `realtime`）；
2. 根据模式自动调整：
   - 光谱 payload 偏移；
   - 背景扫描方式；
3. CLI 接口保持一致；
4. 未来可插入“自动识别”逻辑而不改动主框架。

---

## 三、统一的结构设计

```bash
srs_extractor/
│
├── srs_extractor/
│   ├── __init__.py
│   ├── fast_scan.py
│   ├── realtime.py
│   ├── common.py
│   ├── bg_fast.py
│   ├── bg_realtime.py
│   ├── spectra_matrix.py
│   ├── time_axis.py
│   └── extract_core.py
│
├── cli.py
├── README.md
├── requirements.txt
└── setup.py
```

---

## 四、统一入口 `cli.py`

```python
import argparse
from .extract_core import run_extraction

def main():
    parser = argparse.ArgumentParser(
        description="Extract spectra and background from Omnic SRS files (Rapid Scan / Realtime)"
    )
    parser.add_argument("srs", help="Path to .srs file")
    parser.add_argument("--mode", choices=["fast", "realtime"], required=True,
                        help="Specify SRS format: 'fast' (Omnic Rapid Scan) or 'realtime'")
    parser.add_argument("--outdir", default="output", help="Output directory for results")
    parser.add_argument("--start", type=float, help="Wavenumber start (cm⁻¹)")
    parser.add_argument("--end", type=float, help="Wavenumber end (cm⁻¹)")
    args = parser.parse_args()

    run_extraction(args.srs, mode=args.mode, outdir=args.outdir,
                   start_wn=args.start, end_wn=args.end)
```

---

## 五、核心提取逻辑 `extract_core.py`

整合 fast 与 realtime 的逻辑：

```python
import os
import numpy as np
from .common import read_all_bytes, find_all, FRAME_MARKER_HEX
from .bg_fast import detect_payloads_by_markers, extract_background_matrix
from .bg_realtime import find_first_background_offset, extract_background_first

def run_extraction(srs_path, mode="fast", outdir="output", start_wn=None, end_wn=None):
    srs = read_all_bytes(srs_path)
    os.makedirs(outdir, exist_ok=True)
    marker = bytes.fromhex(FRAME_MARKER_HEX)
    print(f"文件大小: {len(srs):,} bytes")
    print(f"运行模式: {mode}")

    # Step 1: 时间轴
    from .time_axis import extract_time_axis
    time_axis, frame_positions = extract_time_axis(srs, marker)
    if len(frame_positions) < 2:
        print("⚠ 帧标记不足，终止。")
        return

    # Step 2: 光谱矩阵
    payload_offset = 80 if mode == "fast" else 84
    from .spectra_matrix import extract_spectra_matrix
    spectra = extract_spectra_matrix(srs, frame_positions, payload_offset)
    if spectra is None:
        return

    # Step 3: 波数轴
    if start_wn is None or end_wn is None:
        try:
            start_wn = float(input("请输入波数起点 (cm⁻¹): ").strip())
            end_wn = float(input("请输入波数终点 (cm⁻¹): ").strip())
        except Exception:
            print("❌ 波数输入无效。终止。")
            return
    wn_axis = np.linspace(start_wn, end_wn, spectra.shape[1])

    # Step 4: 保存时间序列光谱
    out_ts = os.path.join(outdir, "spectra_timeseries.csv")
    if time_axis is not None and len(time_axis) >= spectra.shape[0]:
        data_with_time = np.column_stack((time_axis[:spectra.shape[0]], spectra))
        header = "time," + ",".join(f"{x:.3f}" for x in wn_axis)
        np.savetxt(out_ts, data_with_time, delimiter=",", header=header, comments="")
    else:
        header = ",".join(f"{x:.3f}" for x in wn_axis)
        np.savetxt(out_ts, spectra, delimiter=",", header=header, comments="")
    print(f"📄 已保存时间分辨光谱: {out_ts}")

    # Step 5: 背景提取
    if mode == "fast":
        bg_offsets = detect_payloads_by_markers(srs)
        bg_matrix = extract_background_matrix(srs, bg_offsets, spectra.shape[1])
    else:
        bg_matrix, off = extract_background_first(
            srs, target_npts=spectra.shape[1],
            interval_bytes=9040, offset_adjust=-404, scan_step=512
        )

    if bg_matrix is not None:
        out_bg = os.path.join(outdir, "background.csv")
        header = "wavenumber" + "".join([f",bg{i+1}" for i in range(bg_matrix.shape[0])])
        out_mat = np.column_stack([wn_axis, bg_matrix.T])
        np.savetxt(out_bg, out_mat, delimiter=",", header=header, comments="")
        print(f"📄 已保存背景文件: {out_bg}")
    else:
        print("⚠ 未导出背景。")
```

---

## 六、用户使用示例

```bash
# Rapid Scan
srs-extract sample_rapid.srs --mode fast --start 650 --end 4000

# Realtime
srs-extract sample_rt.srs --mode realtime
```

---

## 七、未来扩展接口（自动识别模式）

```python
if args.mode == "auto":
    from .file_identify import guess_srs_type
    args.mode = guess_srs_type(args.srs)
```

未来可在 `file_identify.py` 中实现特征字节判定逻辑。

---

## 八、总结与优势

| 特性 | 说明 |
|------|------|
| 模式参数显式可控 | 避免误判文件类型 |
| payload 偏移可配置 | 兼容不同格式 |
| 背景提取模块化 | fast / realtime 各自独立 |
| 架构清晰 | 核心逻辑集中在 `extract_core.py` |
| 高迁移性 | pip install . 后命令行可直接运行 |

---

## 九、最终命令行体验

```bash
srs-extract demo.srs --mode realtime --outdir results
```

输出：
```
文件大小: 13,482,944 bytes
运行模式: realtime
✅ 解析时间/电位 480 点，范围: 0.0150 ~ 7.1800
✅ 光谱矩阵形状: (480, 1024)
✅ 背景起点: 30208 ；长度: 1024 点
📄 已保存时间分辨光谱: results/spectra_timeseries.csv
📄 已保存背景文件: results/background.csv
```

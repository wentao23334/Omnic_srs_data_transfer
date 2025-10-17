# SRS Extractor

`SRS Extractor` 是一个用于解析 Thermo OMNIC `.srs` 光谱文件的轻量化 Python 包，当前支持 **Rapid Scan (fast)** 与 **Realtime** 两种模式。项目提供统一的命令行接口，可输出时间分辨光谱矩阵和背景光谱。

## 功能速览

- 通过帧标志 (`c6 d7 cd bc b2 c9 d3 da`) 定位光谱帧。
- 根据模式自动选择 payload 偏移（fast=80，realtime=84）。
- 自动解析时间/电位轴、生成光谱矩阵。
- 按用户指定波数范围（或交互输入）生成等间距波数轴。
- 导出 `spectra_timeseries.csv`（含时间列）与 `background.csv`。
- fast 模式优先使用 marker 背景识别，自动回退至间隔扫描；realtime 模式始终使用间隔扫描背景逻辑。

## 目录结构

```
SRS Extractor/
├── srs_extractor/
│   ├── __init__.py
│   ├── bg_fast.py
│   ├── bg_realtime.py
│   ├── cli.py
│   ├── common.py
│   ├── extract_core.py
│   ├── spectra_matrix.py
│   └── time_axis.py
├── output_rt_s1e5/          # 示例 smoke test 输出（可删除）
├── fast_scan_extract.py     # 旧脚本（保留备查）
└── real_time_extract.py     # 旧脚本（保留备查）
```

## 环境准备

项目仅依赖 `numpy`。推荐使用 Python 3.9+。

```bash
# 创建并激活虚拟环境（示例：conda）
conda create -n srs_extractor python=3.11 -y
conda activate srs_extractor

# 或使用 venv
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell

pip install numpy
```

## 使用方法

1. 进入目录，此处以`finished/`为例：

   ```bash
   cd finished
   ```

2. 运行 CLI：

   ```bash
   python -m srs_extractor.cli <path/to/file.srs> --mode {fast|realtime} --start 650 --end 4000 --outdir output
   ```

   参数说明：

   | 参数        | 说明                                           |
   |-------------|------------------------------------------------|
   | `srs`       | `.srs` 文件路径，可为绝对或相对路径           |
   | `--mode`    | `fast` 或 `realtime`，用户需手动指定           |
   | `--start`   | 波数起点（cm⁻¹），可省略以改用交互输入        |
   | `--end`     | 波数终点（cm⁻¹），可省略以改用交互输入        |
   | `--outdir`  | 输出目录（默认 `output`，自动创建）           |

3. 输出文件：

   - `spectra_timeseries.csv`：第一列为时间/电位，其余列为各波数点光谱。
   - `background.csv`：第一列为波数轴，其余列为背景光谱（fast 模式可能多条）。

## 模块简介

- `common.py`：共享常量与基础工具（读文件、二进制搜索）。
- `time_axis.py`：解析帧位置并提取时间/电位数组。
- `spectra_matrix.py`：按帧构建光谱矩阵，内部按配置裁剪 payload。
- `bg_fast.py`：fast 模式背景提取，包含 marker 检测与矩阵构建。
- `bg_realtime.py`：realtime 模式背景提取，使用间隔扫描策略。
- `extract_core.py`：统一入口，整合时间轴、光谱矩阵与背景处理。
- `cli.py`：命令行封装，解析参数后调用核心流程。

## 开发者提示

- CLI 可使用 `python -m srs_extractor.cli ...` 直接运行。
- 若需整合至其他项目，可直接 `from srs_extractor.extract_core import run_extraction`。
- 旧脚本依然保留，便于比对或回退；后续可逐步迁移至新包结构。

## 已验证

- 使用 `s1e5_-1.5v.srs`（Realtime）完成 smoke 测试，输出位于 `output_rt_s1e5/`。


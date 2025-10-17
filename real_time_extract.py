# real_time_extract.py
# ---------------------------------------------------------
# 独立版：提取时间轴 + 时间分辨光谱 + 背景光谱（无外部 JSON）
# （已删除“按标记找BG”的全部代码，仅保留按间隔扫描的策略）
# ---------------------------------------------------------

import os
import numpy as np
import argparse

# ========= 默认参数（可通过命令行覆盖） =========
FRAME_MARKER_HEX = "c6 d7 cd bc b2 c9 d3 da"
DEFAULT_POINTS   = 1024    # 用于快速质量判定的采样点数
DEFAULT_BG_INTERVAL = 9040 # 背景块间隔（字节）
DEFAULT_BG_OFFSET   = -404    # 背景起点手动修正（字节）
DEFAULT_BG_SCANSTEP = 512  # 扫描步长（字节）
QUALITY_STD_MIN     = 1e-6 # 判定“像谱”的最小标准差


# ========= 基础工具 =========
def read_all_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def find_all(haystack: bytes, needle: bytes, max_hits=200000):
    out, st = [], 0
    while True:
        i = haystack.find(needle, st)
        if i == -1:
            break
        out.append(i)
        if len(out) >= max_hits:
            break
        st = i + 1
    return out


# ========= 时间轴提取 =========
def extract_time_axis(srs: bytes, frame_marker: bytes):
    positions = find_all(srs, frame_marker)
    if len(positions) < 2:
        print("⚠ 未找到足够帧标志，无法提取时间轴。")
        return None, positions
    time_vals = []
    for pos in positions:
        # 帧头：8字节marker + 8字节ASCII(时间/电位)
        ascii_part = srs[pos + 8 : pos + 16]
        val_str = ascii_part.decode(errors="ignore").strip()
        try:
            val = float(val_str)
        except ValueError:
            val = np.nan
        time_vals.append(val)
    time_vals = np.asarray(time_vals, dtype=float)
    finite = np.isfinite(time_vals)
    if not finite.any():
        print("⚠ 未解析出有效时间值。")
        return None, positions
    print(f"✅ 解析时间/电位 {finite.sum()} 点，范围: {time_vals[finite][0]:.4f} ~ {time_vals[finite][-1]:.4f}")
    return time_vals, positions


# ========= 光谱矩阵提取 =========
def extract_spectra_matrix(srs: bytes, frame_positions: list[int], max_frames=None):
    if len(frame_positions) < 2:
        print("⚠ 帧标记不足，跳过光谱导出。")
        return None
    frames = []
    N = len(frame_positions) - 1
    if max_frames:
        N = min(N, max_frames)

    for i in range(N):
        start = frame_positions[i]
        end   = frame_positions[i + 1]
        if end <= start:
            continue
        # 最小改动：去掉尾部16字节，避免“末尾4点无效”；payload从84开始（按你当前可用设置）
        block   = srs[start : end - 16]
        payload = block[84:]
        arr = np.frombuffer(payload, dtype=np.float32)
        if arr.size > 0:
            frames.append(arr)

    if not frames:
        print("⚠ 未解析到帧数据。")
        return None

    min_len = min(map(len, frames))
    M = np.stack([f[:min_len] for f in frames])
    print(f"✅ 光谱矩阵形状: {M.shape} （行=帧，列=波数点）")
    return M


# ========= 背景：按间隔扫描，仅取第一条 =========
def find_first_background_offset(srs: bytes,
                                 interval_bytes: int,
                                 offset_adjust: int,
                                 scan_step: int,
                                 nprobe_points: int = DEFAULT_POINTS):
    """
    在文件头至末尾-10*interval之间，以 scan_step 为步长扫描，
    读取 nprobe_points 个 float32，使用“有限性+方差”判据挑第一处像谱的片段。
    返回：真实背景数据起点（字节）。
    """
    filesize = len(srs)
    lim = max(0, filesize - 10 * max(interval_bytes, 1))
    first_guess = 0
    while first_guess < lim:
        off = first_guess + offset_adjust
        if 0 <= off < filesize:
            a = np.frombuffer(srs, dtype=np.float32, count=nprobe_points, offset=off)
            if a.size == nprobe_points and np.isfinite(a).all() and np.std(a) > QUALITY_STD_MIN:
                return off
        first_guess += scan_step
    return None


def extract_background_first(srs: bytes, target_npts: int,
                             interval_bytes: int,
                             offset_adjust: int,
                             scan_step: int):
    off = find_first_background_offset(srs, interval_bytes, offset_adjust, scan_step)
    if off is None:
        print("⚠ 未找到背景片段（按间隔扫描失败）。")
        return None, None
    filesize = len(srs)
    npts = min((filesize - off) // 4, target_npts)
    vec = np.frombuffer(srs, dtype=np.float32, count=npts, offset=off)
    if vec.size != npts:
        print("⚠ 背景读取失败（长度不匹配）。")
        return None, off
    print(f"✅ 背景起点: {off} ；长度: {npts} 点")
    return vec[np.newaxis, :], off  # shape (1, npts)


# ========= 主流程 =========
def main():
    ap = argparse.ArgumentParser(description="从 SRS 提取时间分辨光谱与背景（含时间轴 & 手动波数轴）")
    ap.add_argument("srs", help="SRS 文件路径")
    ap.add_argument("--outdir", default="output", help="输出目录")
    # 背景扫描可调参数
    ap.add_argument("--bg-interval", type=int, default=DEFAULT_BG_INTERVAL, help="背景块间隔（字节），默认 9040")
    ap.add_argument("--bg-offset",   type=int, default=DEFAULT_BG_OFFSET,   help="背景起点手动修正（字节），默认 0")
    ap.add_argument("--bg-scan-step",type=int, default=DEFAULT_BG_SCANSTEP, help="扫描步长（字节），默认 512")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    srs = read_all_bytes(args.srs)
    marker = bytes.fromhex(FRAME_MARKER_HEX)

    print(f"文件大小: {len(srs):,} bytes")

    # 1) 时间轴
    time_axis, frame_positions = extract_time_axis(srs, marker)

    # 2) 光谱矩阵
    spectra = extract_spectra_matrix(srs, frame_positions)
    if spectra is None:
        return

    # 3) 手动输入波数轴范围
    try:
        start_wn = float(input("请输入波数起点 (cm⁻¹): ").strip())
        end_wn   = float(input("请输入波数终点 (cm⁻¹): ").strip())
    except Exception:
        print("❌ 波数输入无效，终止。")
        return
    wn_axis = np.linspace(start_wn, end_wn, spectra.shape[1])
    print(f"✅ 生成波数轴 [{wn_axis[0]:.3f} ~ {wn_axis[-1]:.3f}]  点数={len(wn_axis)}")

    # 4) 保存时间分辨光谱（第一列=时间/电位）
    out_ts = os.path.join(args.outdir, "spectra_timeseries.csv")
    if time_axis is not None and len(time_axis) >= spectra.shape[0]:
        data_with_time = np.column_stack((time_axis[: spectra.shape[0]], spectra))
        header = "time," + ",".join(f"{x:.6f}" for x in wn_axis)
        np.savetxt(out_ts, data_with_time, delimiter=",", header=header, comments="")
        print(f"📄 已保存时间分辨光谱: {out_ts}")
    else:
        header = ",".join(f"{x:.6f}" for x in wn_axis)
        np.savetxt(out_ts, spectra, delimiter=",", header=header, comments="")
        print(f"⚠ 时间轴不匹配，未加首列。已保存: {out_ts}")

    # 5) 背景（仅第一条）
    bgM, bg_off = extract_background_first(
        srs,
        target_npts=spectra.shape[1],
        interval_bytes=args.bg_interval,
        offset_adjust=args.bg_offset,
        scan_step=args.bg_scan_step,
    )
    if bgM is not None:
        out_bg = os.path.join(args.outdir, "background.csv")
        header = "wavenumber,bg1"
        out_mat = np.column_stack([wn_axis, bgM[0]])
        np.savetxt(out_bg, out_mat, delimiter=",", header=header, comments="")
        print(f"📄 已保存背景文件: {out_bg}")
    else:
        print("⚠ 未导出背景文件。")


if __name__ == "__main__":
    main()

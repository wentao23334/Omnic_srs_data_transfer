# fast_scan_extract.py
# ---------------------------------------------------------
# 独立版：提取时间轴 + 时间分辨光谱 + 背景光谱（无外部 JSON）
# ---------------------------------------------------------

import os
import numpy as np
import argparse
from collections import defaultdict

# ========= 内置背景定位参数（来自 bg_markers.json） =========
BG_INTERVAL_BYTES = 9040  # 每条背景光谱之间的字节间隔
BG_MARKERS = [
    {"delta_to_payload": 336, "hex": "01 00 00 00 80 08 00 00"},
    {"delta_to_payload": 335, "hex": "00 00 00 80 08 00 00 02"},
    {"delta_to_payload": 334, "hex": "00 00 80 08 00 00 02 00"},
    {"delta_to_payload": 333, "hex": "00 80 08 00 00 02 00 00"},
    {"delta_to_payload": 332, "hex": "80 08 00 00 02 00 00 00"},
]
FRAME_MARKER_HEX = "c6 d7 cd bc b2 c9 d3 da"
DEFAULT_POINTS = 1024


# ========= 工具函数 =========
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

    # 自动检测模式
    first_gap = frame_positions[1] - frame_positions[0]
    if first_gap > 20000:
        payload_offset = 27854
        npts = 1024
        print(f"🔎 检测到新版 fast 模式，使用偏移 {payload_offset} 和 npts={npts}")
    else:
        payload_offset = 80
        npts = 600
        print(f"🔎 检测到旧版 rapid 模式，使用偏移 {payload_offset}")

    # 计算帧间距（用于新版）
    avg_gap = int(np.median(np.diff(frame_positions)))
    print(f"🧩 估计帧间距: {avg_gap} bytes")

    frames = []
    filesize = len(srs)
    for i, pos in enumerate(frame_positions):
        if max_frames and i >= max_frames: 
            break
        start = pos + payload_offset
        end = start + npts * 4
        if end > filesize:
            break
        arr = np.frombuffer(srs[start:end], dtype=np.float32)
        if np.isfinite(arr).all() and np.std(arr) > 1e-6:
            frames.append(arr)

    if not frames:
        print("⚠ 未解析到帧数据。")
        return None

    M = np.vstack(frames)
    print(f"✅ 光谱矩阵形状: {M.shape} （行=帧，列=波数点）")
    return M



# ========= 背景定位与提取 =========
def detect_payloads_by_markers(srs: bytes, markers: list[dict], tol=64, min_sep=8000):
    votes = defaultdict(int)
    for m in markers:
        seq = bytes.fromhex(m["hex"])
        delta = int(m["delta_to_payload"])
        hits = find_all(srs, seq, max_hits=50000)
        for hp in hits:
            pos = hp + delta
            if 0 <= pos < len(srs):
                votes[pos] += 1
    if not votes:
        return []
    items = sorted(votes.items())
    merged = []
    cur_pos, cur_votes = None, 0
    for pos, v in items:
        if cur_pos is None:
            cur_pos, cur_votes = pos, v
        elif abs(pos - cur_pos) <= tol:
            cur_pos = int((cur_pos * cur_votes + pos * v) / (cur_votes + v))
            cur_votes += v
        else:
            merged.append((cur_pos, cur_votes))
            cur_pos, cur_votes = pos, v
    if cur_pos is not None:
        merged.append((cur_pos, cur_votes))
    merged.sort(key=lambda x: (-x[1], x[0]))
    picks = []
    for pos, _ in merged:
        if all(abs(pos - p) >= min_sep for p in picks):
            picks.append(pos)
        if len(picks) >= 4:
            break
    return sorted(picks)


def extract_background_matrix(srs: bytes, payload_offsets: list[int], target_npts: int):
    if not payload_offsets:
        print("⚠ 未能定位背景 payload。")
        return None
    mats = []
    filesize = len(srs)
    for off in payload_offsets:
        npts = min((filesize - off) // 4, target_npts)
        a = np.frombuffer(srs, dtype=np.float32, count=npts, offset=off)
        if a.size == npts:
            mats.append(a)
    if not mats:
        print("⚠ 背景读取失败。")
        return None
    M = np.vstack(mats)
    print(f"✅ 背景矩阵形状: {M.shape}")
    return M


# ========= 主流程 =========
def main():
    ap = argparse.ArgumentParser(description="从 SRS 提取时间分辨光谱与背景（含时间轴 & 自动点数检测）")
    ap.add_argument("srs", help="SRS 文件路径")
    ap.add_argument("--outdir", default="output", help="输出目录")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    srs = read_all_bytes(args.srs)
    marker = bytes.fromhex(FRAME_MARKER_HEX)

    print(f"文件大小: {len(srs):,} bytes")

    # 1️⃣ 提取时间轴 & 帧位置
    time_axis, frame_positions = extract_time_axis(srs, marker)
    if not frame_positions or len(frame_positions) < 2:
        print("❌ 未找到有效帧标志，终止。")
        return

    # 2️⃣ 检测伪帧（例如首帧异常大）
    first_gap = frame_positions[1] - frame_positions[0]
    if first_gap > 20000:
        print(f"⚙ 检测到首帧异常，差距={first_gap} bytes，自动跳过第 0 帧。")
        frame_positions = frame_positions[1:]
        if time_axis is not None and len(time_axis) > len(frame_positions):
            time_axis = time_axis[1:]

    # 3️⃣ 自动估算帧间距 & 光谱点数
    frame_spacing = int(np.median(np.diff(frame_positions[:10]))) if len(frame_positions) > 10 else 3572
    header_offset = 80  # payload 起点，旧版为 80
    npts_est = max(100, (frame_spacing - header_offset) // 4)

    print(f"🧩 估计帧间距: {frame_spacing} bytes")
    print(f"🧩 自动推算每帧光谱点数 ≈ {npts_est}")

    payload_offset = header_offset
    npts_guess = npts_est

    # 4️⃣ 提取光谱矩阵
    spectra = []
    N = len(frame_positions) - 1
    for i in range(N):
        start = frame_positions[i]
        end = frame_positions[i + 1]
        if end <= start:
            continue
        block = srs[start + payload_offset:end-16]
        arr = np.frombuffer(block, dtype=np.float32)
        if arr.size >= npts_guess:
            arr = arr[:npts_guess]
        if np.isfinite(arr).any():
            spectra.append(arr)

    if not spectra:
        print("⚠ 未解析到光谱数据。")
        return

    min_len = min(map(len, spectra))
    M = np.stack([f[:min_len] for f in spectra])
    print(f"✅ 光谱矩阵形状: {M.shape} （行=帧，列=波数点）")

    # 5️⃣ 用户输入波数轴
    try:
        start_wn = float(input("请输入波数起点 (cm⁻¹): ").strip())
        end_wn = float(input("请输入波数终点 (cm⁻¹): ").strip())
    except Exception:
        print("❌ 波数输入无效，终止。")
        return
    wn_axis = np.linspace(start_wn, end_wn, M.shape[1])
    print(f"✅ 生成波数轴 [{wn_axis[0]:.3f} ~ {wn_axis[-1]:.3f}]  点数={len(wn_axis)}")

    # 6️⃣ 保存时间分辨光谱
    out_ts = os.path.join(args.outdir, "spectra_timeseries.csv")
    if time_axis is not None and len(time_axis) >= M.shape[0]:
        data_with_time = np.column_stack((time_axis[: M.shape[0]], M))
        header = "time," + ",".join(f"{x:.6f}" for x in wn_axis)
        np.savetxt(out_ts, data_with_time, delimiter=",", header=header, comments="")
        print(f"📄 已保存时间分辨光谱: {out_ts}")
    else:
        header = ",".join(f"{x:.6f}" for x in wn_axis)
        np.savetxt(out_ts, M, delimiter=",", header=header, comments="")
        print(f"⚠ 时间轴不匹配，未加首列。已保存: {out_ts}")

    # 7️⃣ 背景定位
    bg_offsets = detect_payloads_by_markers(srs, BG_MARKERS)
    if not bg_offsets:
        print("未找到背景标记，尝试按间隔推测…")
        first_guess = 0
        while first_guess < len(srs) - 10 * BG_INTERVAL_BYTES:
            arr = np.frombuffer(srs, dtype=np.float32, count=DEFAULT_POINTS, offset=first_guess)
            if np.isfinite(arr).all() and np.std(arr) > 1e-6:
                bg_offsets = [first_guess + i * BG_INTERVAL_BYTES for i in range(3)]
                break
            first_guess += 512

    if bg_offsets:
        print("定位到背景 payload 起点：")
        for i, p in enumerate(bg_offsets, 1):
            print(f"  BG#{i}  @SRS {p}")
    else:
        print("⚠ 未找到背景标记。")

    # 8️⃣ 提取背景矩阵
    bgM = extract_background_matrix(srs, bg_offsets, M.shape[1])
    if bgM is not None:
        out_bg = os.path.join(args.outdir, "background.csv")
        header = "wavenumber" + "".join([f",bg{i+1}" for i in range(bgM.shape[0])])
        out_mat = np.column_stack([wn_axis, bgM.T])
        np.savetxt(out_bg, out_mat, delimiter=",", header=header, comments="")
        print(f"📄 已保存背景文件: {out_bg}")
    else:
        print("⚠ 未导出背景文件。")



if __name__ == "__main__":
    main()

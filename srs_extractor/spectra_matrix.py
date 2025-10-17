import numpy as np
from typing import List, Optional


def extract_spectra_matrix(
    srs: bytes,
    frame_positions: List[int],
    payload_offset: int,
    max_frames: Optional[int] = None,
):
    if len(frame_positions) < 2:
        print("帧标记不足，跳过光谱导出")
        return None
    frames = []
    N = len(frame_positions) - 1
    if max_frames:
        N = min(N, max_frames)

    for i in range(N):
        start = frame_positions[i]
        end = frame_positions[i + 1]
        if end <= start:
            continue
        # drop last 16 bytes; payload starts at offset
        block = srs[start : end - 16]
        payload = block[payload_offset:]
        arr = np.frombuffer(payload, dtype=np.float32)
        if arr.size > 0:
            frames.append(arr)

    if not frames:
        print("未解析到帧数据")
        return None

    min_len = min(map(len, frames))
    M = np.stack([f[:min_len] for f in frames])
    print(f"光谱矩阵形状: {M.shape} （行=帧，列=波数点）")
    return M

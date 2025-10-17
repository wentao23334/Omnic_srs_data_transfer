import numpy as np
from collections import defaultdict
from typing import List
from .common import find_all

# Copied from fast_scan_extract defaults
BG_INTERVAL_BYTES = 9040
BG_MARKERS = [
    {"delta_to_payload": 336, "hex": "01 00 00 00 80 08 00 00"},
    {"delta_to_payload": 335, "hex": "00 00 00 80 08 00 00 02"},
    {"delta_to_payload": 334, "hex": "00 00 80 08 00 00 02 00"},
    {"delta_to_payload": 333, "hex": "00 80 08 00 00 02 00 00"},
    {"delta_to_payload": 332, "hex": "80 08 00 00 02 00 00 00"},
]


def detect_payloads_by_markers(srs: bytes, markers: List[dict] = BG_MARKERS, tol: int = 64, min_sep: int = 8000):
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


def extract_background_matrix(srs: bytes, payload_offsets: List[int], target_npts: int):
    if not payload_offsets:
        print("未能定位背景 payload")
        return None
    mats = []
    filesize = len(srs)
    for off in payload_offsets:
        npts = min((filesize - off) // 4, target_npts)
        a = np.frombuffer(srs, dtype=np.float32, count=npts, offset=off)
        if a.size == npts:
            mats.append(a)
    if not mats:
        print("背景读取失败")
        return None
    M = np.vstack(mats)
    print(f"背景矩阵形状: {M.shape}")
    return M

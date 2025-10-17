import numpy as np
from .common import DEFAULT_POINTS, QUALITY_STD_MIN


def find_first_background_offset(
    srs: bytes,
    interval_bytes: int = 9040,
    offset_adjust: int = -404,
    scan_step: int = 512,
    nprobe_points: int = DEFAULT_POINTS,
):
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


def extract_background_first(
    srs: bytes,
    target_npts: int,
    interval_bytes: int = 9040,
    offset_adjust: int = -404,
    scan_step: int = 512,
):
    off = find_first_background_offset(srs, interval_bytes, offset_adjust, scan_step)
    if off is None:
        print("未找到背景片段（按间隔扫描失败）")
        return None, None
    filesize = len(srs)
    npts = min((filesize - off) // 4, target_npts)
    vec = np.frombuffer(srs, dtype=np.float32, count=npts, offset=off)
    if vec.size != npts:
        print("背景读取失败（长度不匹配）")
        return None, off
    print(f"背景起点: {off} ；长度 {npts}")
    return vec[np.newaxis, :], off


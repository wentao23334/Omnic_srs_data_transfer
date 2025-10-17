import numpy as np

# Shared constants
FRAME_MARKER_HEX = "c6 d7 cd bc b2 c9 d3 da"
DEFAULT_POINTS = 1024
QUALITY_STD_MIN = 1e-6


def read_all_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def find_all(haystack: bytes, needle: bytes, max_hits: int = 200000):
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


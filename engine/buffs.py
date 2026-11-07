"""Buff icons at the top right of the game, read from a screenshot.

A buff is told by a FINGERPRINT (assets/buff_table.json): the blurred colour at a few dozen points
of its icon, measured at the game's 1080 p size, with the points under the countdown digits left
out. No game art is kept. find() says where on a strip of the screen a known buff is.
"""
import json

import cv2
import numpy as np

REF_H = 1080
BLUR = 4
STRIP_W, STRIP_H = 0.55, 110    # share of the window's width (from its right edge), px tall at 1080 p
ACCEPT = 30.0                   # RMS colour distance (0-255) a match must stay under


def fingerprint(icon_bgr, digits, grid=12):
    """Points (x, y, b, g, r) of an icon picture cut tight to its frame, at 1080 p size.
    digits: (x0, y0, x1, y1) where the countdown sits, as a share of the icon."""
    h, w = icon_bgr.shape[:2]
    soft = cv2.blur(icon_bgr.astype(np.float32), (BLUR, BLUR))
    dx0, dy0, dx1, dy1 = digits
    pts = []
    for row in range(grid):
        for col in range(grid):
            fx, fy = (col + 0.5) / grid, (row + 0.5) / grid
            if dx0 <= fx <= dx1 and dy0 <= fy <= dy1:
                continue
            x, y = int(fx * w), int(fy * h)
            pts.append([x, y, *(int(round(v)) for v in soft[y, x])])
    return {"w": w, "h": h, "points": pts}


class BuffTable:
    def __init__(self, items):
        self.items = items

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))


def strip_box(window_w, window_h):
    """(x, y, w, h) of the part of the window where buffs sit."""
    w = int(window_w * STRIP_W)
    return window_w - w, 0, w, int(STRIP_H * window_h / REF_H)


def match(img, item):
    """(distance, x, y) of the best place for item in img (already at 1080 p size), or None."""
    w, h = item["w"], item["h"]
    H, W = img.shape[:2]
    if H < h or W < w:
        return None
    soft = cv2.blur(img.astype(np.float32), (BLUR, BLUR))
    pts = [(x, y, np.array(bgr, np.float32)) for x, y, *bgr in item["points"]]

    def score(x0, y0, x1, y1, step):
        total = 0
        for x, y, v in pts:
            d = soft[y0 + y:y1 + y:step, x0 + x:x1 + x:step] - v
            total = total + (d * d).sum(2)
        return total / (3 * len(pts))

    coarse = score(0, 0, W - w + 1, H - h + 1, 2)
    cy, cx = np.unravel_index(int(np.argmin(coarse)), coarse.shape)
    x0, y0 = max(0, 2 * cx - 2), max(0, 2 * cy - 2)
    fine = score(x0, y0, min(W - w + 1, 2 * cx + 3), min(H - h + 1, 2 * cy + 3), 1)
    y, x = np.unravel_index(int(np.argmin(fine)), fine.shape)
    return float(np.sqrt(fine[y, x])), int(x0 + x), int(y0 + y)


def find(img, window_h, table):
    """{name: (x, y, w, h) in img} of the known buffs showing on img (a strip of the screen)."""
    k = REF_H / window_h
    ref = img if abs(k - 1) < 0.01 else cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    found = {}
    for name, item in table.items.items():
        m = match(ref, item)
        if m and m[0] < item.get("accept", ACCEPT):
            _, x, y = m
            found[name] = (int(x / k), int(y / k), int(item["w"] / k), int(item["h"] / k))
    return found

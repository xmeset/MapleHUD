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
ACCEPT = 0.80                   # how alike (correlation) a match must be at least
BANDS = 6                       # the icon is compared in this many bands, top to bottom
FRAME_DARK, FRAME_STEP = 120, 40    # the frame is darker than this, and this much darker than just inside it


def fingerprint(icon_bgr, digits, grid=16, ring=3):
    """Points (x, y, b, g, r) of an icon picture cut tight to its frame, at 1080 p size.
    digits: (x0, y0, x1, y1) where the countdown sits, as a share of the icon. Points under it and
    within `ring` px of the edge (where the game shows through the rounded corners) are left out."""
    h, w = icon_bgr.shape[:2]
    soft = cv2.blur(icon_bgr.astype(np.float32), (BLUR, BLUR))
    dx0, dy0, dx1, dy1 = digits
    pts = []
    for row in range(grid):
        for col in range(grid):
            fx, fy = (col + 0.5) / grid, (row + 0.5) / grid
            x, y = int(fx * w), int(fy * h)
            if dx0 <= fx <= dx1 and dy0 <= fy <= dy1 or not (ring <= x < w - ring and ring <= y < h - ring):
                continue
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


def _frame_spots(w, h):
    """Points on the icon's dark frame (left, right and bottom: the top can be under the game's FPS counter)
    and just inside it, as ([(x, y)], [(x, y)])."""
    rows = range(8, h - 8, 3)
    cols = range(8, w - 8, 3)
    edge = [(1, y) for y in rows] + [(w - 2, y) for y in rows] + [(x, h - 2) for x in cols]
    inner = [(5, y) for y in rows] + [(w - 6, y) for y in rows] + [(x, h - 6) for x in cols]
    return edge, inner


def match(img, item):
    """(similarity, x, y) of the best place for item in img (already at 1080 p size), or None.

    Similarity is the correlation of the colours at the item's points, worked out band by band
    (top to bottom) so a band dimmed as a whole still matches: the game greys a buff icon from the top
    down as its time runs out. The worst band doesn't count (it may be under the FPS counter, or half
    greyed), and only a place with a dark frame round it counts, so a blurry background can't pass."""
    w, h = item["w"], item["h"]
    H, W = img.shape[:2]
    if H < h or W < w:
        return None
    soft = cv2.blur(img.astype(np.float32), (BLUR, BLUR))
    grey = cv2.erode(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32), np.ones((3, 3), np.uint8))
    bright = cv2.dilate(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32), np.ones((3, 3), np.uint8))
    groups = []
    for b in range(BANDS):
        pts = [p for p in item["points"] if b * h / BANDS <= p[1] < (b + 1) * h / BANDS]
        ref = np.array([p[2:] for p in pts], np.float32)
        groups.append((pts, (ref - ref.mean()) / (np.linalg.norm(ref - ref.mean()) or 1)))
    edge, inner = _frame_spots(w, h)

    def score(x0, y0, x1, y1, step):
        bands = []
        for pts, ref in groups:
            s1 = s2 = sx = 0
            for (x, y, *_), v in zip(pts, ref):
                patch = soft[y0 + y:y1 + y:step, x0 + x:x1 + x:step]
                s1 = s1 + patch.sum(2)
                s2 = s2 + (patch * patch).sum(2)
                sx = sx + (patch * v).sum(2)
            bands.append(sx / np.sqrt(np.maximum(s2 - s1 * s1 / ref.size, 1e-6)))
        bands = np.sort(np.stack(bands), axis=0)[1:].mean(0)
        dark = sum(grey[y0 + y:y1 + y:step, x0 + x:x1 + x:step] for x, y in edge) / len(edge)
        light = sum(bright[y0 + y:y1 + y:step, x0 + x:x1 + x:step] for x, y in inner) / len(inner)
        return np.where((dark < FRAME_DARK) & (light - dark > FRAME_STEP), bands, 0)

    coarse = score(0, 0, W - w + 1, H - h + 1, 2)
    cy, cx = np.unravel_index(int(np.argmax(coarse)), coarse.shape)
    x0, y0 = max(0, 2 * cx - 2), max(0, 2 * cy - 2)
    fine = score(x0, y0, min(W - w + 1, 2 * cx + 3), min(H - h + 1, 2 * cy + 3), 1)
    y, x = np.unravel_index(int(np.argmax(fine)), fine.shape)
    return float(fine[y, x]), int(x0 + x), int(y0 + y)


def find(img, window_h, table):
    """{name: (x, y, w, h, similarity) in img} of the known buffs showing on img (a strip of the screen)."""
    k = REF_H / window_h
    ref = img if abs(k - 1) < 0.01 else cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    found = {}
    for name, item in table.items.items():
        m = match(ref, item)
        if m and m[0] >= item.get("accept", ACCEPT):
            s, x, y = m
            found[name] = (int(x / k), int(y / k), int(item["w"] / k), int(item["h"] / k), s)
    return found

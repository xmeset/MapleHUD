import cv2
import numpy as np

import exp_font

STRIP = 0.09
CHARS = "0123456789/"
TX = np.arange(0.0, 2.0, 0.25)
TY = np.arange(-1.0, 1.01, 0.25)
MIN_SCORE = 0.8
_bank = {}


def _pictures():
    font = exp_font.load()
    out = {}
    for ch in "0123456789":
        g = font["glyphs"][ch]
        pic = np.zeros((7, g["w"]), np.float32)
        y = g["y0"] + 6
        pic[y:y + g["h"]] = np.array(g["rows"], np.float32) / 255
        out[ch] = pic
    out["/"] = np.array([[0, 0, 0], [0, 0, 1], [0, 0, 1], [0, 1, 0], [0, 1, 0], [1, 0, 0], [1, 0, 0]], np.float32)
    return out


PICS = _pictures()


def _unit(a):
    a = a - a.mean(axis=-1, keepdims=True)
    return a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-6)


def bank(scale, h, w, oy=0):
    key = (round(scale, 3), h, w, oy)
    if key not in _bank:
        rows, labels = [], []
        for ch, pic in PICS.items():
            for tx in TX:
                for ty in TY:
                    rows.append(exp_font.sample(pic, scale, tx, oy + ty, (h, w)).reshape(-1))
                    labels.append(ch)
        _bank[key] = (_unit(np.array(rows, np.float32)), labels)
        if len(_bank) > 64:
            _bank.pop(next(iter(_bank)))
    return _bank[key]


def _masks(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    green = (s >= 90) & (v >= 110) & (h >= 26) & (h <= 50)
    white = (s < 70) & (v >= 140)
    return green, white, v


def _brackets(green):
    n, _, stats, _ = cv2.connectedComponentsWithStats(green.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if h >= 5 and w <= 0.75 * h and a >= h:
            out.append((x, y, w, h))
    return out


def find_fields(bgr):
    """[(x0, y0, x1, y1)] inside each [...] on the lowest text line, left to right (HP, MP, EXP)."""
    green, _, _ = _masks(bgr)
    br = _brackets(green)
    if len(br) < 4:
        return []
    lines = []
    for b in sorted(br, key=lambda b: b[1] + b[3] / 2):
        cy = b[1] + b[3] / 2
        if lines and abs(lines[-1][0] - cy) <= 0.3 * b[3]:
            lines[-1][1].append(b)
        else:
            lines.append([cy, [b]])
    lines = [ln for ln in lines if len(ln[1]) >= 4]
    if not lines:
        return []
    row = sorted(lines[-1][1], key=lambda b: b[0])
    fields = []
    for a, b in zip(row[0::2], row[1::2]):
        if b[0] - (a[0] + a[2]) < 3:
            continue
        fields.append((a[0] + a[2], min(a[1], b[1]), b[0], max(a[1] + a[3], b[1] + b[3])))
    return fields


def read_field(bgr, field, scale=None):
    """Text inside one [...] field, e.g. '829/829', or None if it isn't clearly readable."""
    x0, y0, x1, y1 = field
    scale = scale or (y1 - y0) / 7
    pad = max(1, round(scale))
    top = max(0, y0 - pad)
    crop = bgr[top:y1 + pad, x0:x1]
    _, white, v = _masks(crop)
    vv = v.astype(np.float32)
    cols = white.any(axis=0)
    h, w = vv.shape
    gw = int(np.ceil(6 * scale)) + 1
    runs, x = [], 0
    while x < len(cols):
        if not cols[x]:
            x += 1
            continue
        s = x
        while x < len(cols) and cols[x]:
            x += 1
        n = round((x - s + scale) / (6 * scale))
        if x - s > 7 * scale and n > 1:
            step = (x - s) / n
            runs += [round(s + i * step) for i in range(n)]
        else:
            runs.append(s)
    if not runs:
        return None
    mat, labels = bank(scale, h, gw, y0 - top)
    text = ""
    for s in runs:
        patch = np.zeros((h, gw), np.float32)
        a, b = s - 1, min(w, s - 1 + gw)
        src = vv[:, max(0, a):b]
        patch[:, max(0, -a):max(0, -a) + src.shape[1]] = src
        nxt = [r for r in runs if r > s]
        if nxt and nxt[0] - 1 - a < gw:
            patch[:, nxt[0] - 1 - a:] = patch[:, :1].min()
        scores = mat @ _unit(patch.reshape(1, -1))[0]
        i = int(scores.argmax())
        if scores[i] < MIN_SCORE:
            return None
        text += labels[i]
    return text


def parse(text):
    if not text or text.count("/") != 1:
        return None
    a, b = text.split("/")
    if not a.isdigit() or not b.isdigit() or len(b) > 6:
        return None
    cur, mx = int(a), int(b)
    if mx <= 0 or cur > mx:
        return None
    return cur, mx


def read_hpmp(bgr, scale=None):
    """((hp, max), (mp, max)) from a picture of the bottom of the game window, or None."""
    fields = find_fields(bgr)
    if len(fields) < 2:
        return None
    hp = parse(read_field(bgr, fields[0], scale))
    mp = parse(read_field(bgr, fields[1], scale))
    if not hp or not mp:
        return None
    return hp, mp

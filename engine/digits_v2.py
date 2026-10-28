"""Digit reader v2: reads the EXP number and percentage by drawing the game's own font (assets/exp_font.json).

Today's reader (maple_exp.read_layout) rescales every digit to a standard size and compares it with saved
examples. This one does the reverse: the game paints the bar text in a 5 x 7 pixel font and smooths it up with
plain bilinear filtering, so we paint each digit the same way at the screen's scale and compare it with the real
pixels. Nothing is rescaled, and the whole line is checked too (the digits must sit where the font puts them,
and the commas, the dot, the % sign and the brackets must match as well). Anything unclear gives None.

The line is found by maple_exp.find_exp (a Layout: where the digits are, roughly). Here we only fit three
numbers: the scale, and the line's offset across and down, to a quarter of a pixel. Pure numpy and OpenCV.
"""
import math

import cv2
import numpy as np

import exp_font

DIGITS = "0123456789"
S_STEP = 1.005              # scales are tried in steps of 0.5%, so the drawn digits can be reused between looks
MIN_SCORE = 0.80            # correlation each digit needs with the digit it was read as
MIN_LEAD = 0.025            # ...and how far ahead of the runner-up it must be (clean frames lead by 0.06+)
MIN_LINE = 0.85             # correlation of the whole drawn line with the real one
MIN_LABEL = 0.80            # ...and of the label "EXP." before it (it tells if a first digit was lost)
MIN_OPEN = 0.70             # ...and of the "[" on a bar with only a percentage (nothing else tells if its first digit was lost)
MAX_EXP_DIGITS = 12
BLURS = (0.0, 0.7, 1.2)     # extra smoothing (screen pixels) to try, in order, when the exact font doesn't match
_banks = {}                 # (scale step, x phase, y phase) -> (rows, cols, matrix of the 10 drawn digits)


def _unit(a):
    """Rows with their mean taken off and scaled to length 1, so a dot product is a correlation."""
    a = a - a.mean(axis=-1, keepdims=True)
    return a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-6)


def _soften(pic, blur, pad=0):
    """The drawn picture with the extra smoothing of a picture that was resized or recompressed on the way
    to us (blur = the smoothing in screen pixels). `pad` pixels of the margin are cut off after blurring."""
    if blur:
        pic = cv2.GaussianBlur(pic, (0, 0), blur, borderType=cv2.BORDER_REPLICATE)
    return pic[pad:pic.shape[0] - pad, pad:pic.shape[1] - pad] if pad else pic


def _bank(font, k, qx, qy, blur=0.0):
    """The ten digits drawn at scale S_STEP**k, their cell starting a quarter-pixel phase (qx, qy) into the
    window. Cached: the same few come back on every look."""
    key = (k, qx, qy, blur)
    got = _banks.get(key)
    if got is None:
        s = S_STEP ** k
        mx = my = math.ceil(0.5 * s)                 # room for the smoothing around the digit
        cols, rows = mx + math.ceil(5.5 * s), my + math.ceil(7.5 * s)
        cells = []
        for d in DIGITS:
            g = font["glyphs"][d]
            pic = np.zeros((font["digit_height"], 6), np.float32)
            pic[:g["h"], g["x0"]:g["x0"] + g["w"]] = np.array(g["rows"], np.float32) / 255
            pad = math.ceil(3 * blur)
            drawn = exp_font.sample(pic, s, pad + mx + qx / 4, pad + my + qy / 4, (rows + 2 * pad, cols + 2 * pad))
            cells.append(_soften(drawn, blur, pad).reshape(-1))
        if len(_banks) > 3000:
            _banks.clear()
        got = _banks[key] = (rows, cols, mx, my, _unit(np.stack(cells)))
    return got


def _plan(font, n_exp, n_pct):
    """The shape of the line "12,345 [67.89%]" for that many digits: the cell start of each digit (1x), the
    text with placeholder digits, and where its ink ends."""
    pct = "8" * n_pct
    text = ("{:,}".format(int("8" * n_exp)) + " " if n_exp else "") + "[" + pct[:-2] + "." + pct[-2:] + "%]"
    items = exp_font.glyph_positions(text, font)
    pens = [pen for ch, pen, _, _ in items if ch in DIGITS]
    _, _, ink, g = items[-1]
    return text, pens, ink + g["w"], items[0][2]


def _score(font, V, k, tx, ty, pens, blur=0.0):
    """Score every digit position against all ten digits. -> (total of the best scores, matrix of scores),
    or None if the line runs off the picture."""
    s = S_STEP ** k
    iy = math.floor(ty)
    qy = int(round((ty - iy) * 4))
    if qy == 4:
        iy, qy = iy + 1, 0
    out = []
    for pen in pens:
        x = tx + s * pen
        ix = math.floor(x)
        qx = int(round((x - ix) * 4))
        if qx == 4:
            ix, qx = ix + 1, 0
        rows, cols, mx, my, bank = _bank(font, k, qx, qy, blur)
        y0, x0 = iy - my, ix - mx
        if y0 < 0 or x0 < 0 or y0 + rows > V.shape[0] or x0 + cols > V.shape[1]:
            return None
        out.append(_unit(V[y0:y0 + rows, x0:x0 + cols].reshape(-1)) @ bank.T)
    out = np.array(out)
    return float(out.max(axis=1).sum()), out


def _fit(font, V, pens, right, ink_right, cy, ks, blur=0.0):
    """Search the scale step, the line's offset across (dx) and down (dy) for the best total score.
    -> (total, scores, k, tx, ty) or None."""
    best = None

    def try_(k, dx, dy):
        nonlocal best
        s = S_STEP ** k
        tx = right - s * ink_right + dx
        ty = cy - 3.5 * s + dy
        got = _score(font, V, k, tx, ty, pens, blur)
        if got and (best is None or got[0] > best[0]):
            best = (got[0], got[1], k, tx, ty, dx, dy)
        return got

    for k in ks:
        try_(k, 0.0, 0.0)
    if best is None:
        return None
    kstep, dstep = 1, 0.5
    while True:
        _, _, k, _, _, dx, dy = best
        before = best[0]
        for move in ((kstep, 0, 0), (-kstep, 0, 0), (0, dstep, 0), (0, -dstep, 0), (0, 0, dstep), (0, 0, -dstep)):
            try_(k + move[0], dx + move[1], dy + move[2])
        if best[0] > before + 1e-6:
            continue
        if dstep > 0.25:
            dstep = 0.25
            continue
        break
    return best[:5]


def _line_score(font, V, text, k, tx, ty, blur=0.0):
    """How well the whole drawn line (digits, commas, dot, %, brackets) matches the real pixels."""
    s = S_STEP ** k
    pic, _ = exp_font.canvas(text, font)
    x0, y0 = math.floor(tx - 1.5 * s), math.floor(ty - 1.5 * s)
    w, h = math.ceil(pic.shape[1] * s + 3 * s) + 1, math.ceil(pic.shape[0] * s + 3 * s) + 1
    if x0 < 0 or y0 < 0 or y0 + h > V.shape[0] or x0 + w > V.shape[1]:
        return 0.0
    drawn = _soften(exp_font.sample(pic, s, tx - x0, ty - y0, (h, w)), blur)
    return float(_unit(drawn.reshape(-1)) @ _unit(V[y0:y0 + h, x0:x0 + w].reshape(-1)))


def _label_score(font, V, k, tx, ty, blur=0.0):
    """How well the label "EXP." just before the first digit matches. The layout can lose the first digit(s);
    the rest still looks like a clean line, but then the label isn't where it should be (it sits a fixed
    distance before the first digit), so this tells."""
    s = S_STEP ** k
    lab = font["label"]
    pic = np.array(lab["rows"], np.float32) / 255
    left, top = tx + lab["dx"] * s, ty + lab["dy"] * s
    x0, x1 = math.ceil(left + 0.5 * s), math.floor(left + (lab["w"] - 0.5) * s)
    y0, y1 = math.ceil(top + 0.5 * s), math.floor(top + (lab["h"] - 0.5) * s)
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0 or y1 > V.shape[0] or x1 > V.shape[1]:
        return 0.0
    drawn = _soften(exp_font.sample(pic, s, left - x0, top - y0, (y1 - y0, x1 - x0)), blur)
    return float(_unit(drawn.reshape(-1)) @ _unit(V[y0:y1, x0:x1].reshape(-1)))


def _open_score(font, V, k, tx, ty, blur=0.0):
    """How well the "[" sits where the drawn line puts it. On a bar with only a percentage the digits are placed
    from the right-hand "]", so a lost first digit ("36.62" read as "6.62") moves the "[" one slot away from
    where the real one is: this is the only thing that tells."""
    s = S_STEP ** k
    pic, _ = exp_font.canvas("[", font)
    x0, y0 = math.floor(tx - 1.5 * s), math.floor(ty - 1.5 * s)
    w, h = math.ceil(pic.shape[1] * s + 3 * s) + 1, math.ceil(pic.shape[0] * s + 3 * s) + 1
    if x0 < 0 or y0 < 0 or y0 + h > V.shape[0] or x0 + w > V.shape[1]:
        return 0.0
    drawn = _soften(exp_font.sample(pic, s, tx - x0, ty - y0, (h, w)), blur)
    return float(_unit(drawn.reshape(-1)) @ _unit(V[y0:y0 + h, x0:x0 + w].reshape(-1)))


def _pct_cells(lay):
    """The digits inside the brackets: drops the '%' sign right before the ']' (as maple_exp._pct_cells)."""
    return [c for c in lay.pct if lay.box[2] - c[0] > 1.5 * lay.gh]


def _read(font, lay, blur, info):
    """One try at a given amount of extra smoothing. -> (exp, pct) | (None, pct) | None"""
    n_exp, n_pct = len(lay.exp), len(_pct_cells(lay))
    text, pens, ink_right, ink_left = _plan(font, n_exp, n_pct)
    right = lay.box[2]
    # Scale from the width of the whole line when there's a number; a bar with only a percentage has little
    # to measure, so the digit height (a bit too large: it includes the smoothing) gives the start there.
    if n_exp:
        k0 = round(math.log((right - lay.box[0]) / (ink_right - ink_left)) / math.log(S_STEP))
        ks = [k0 - 2, k0, k0 + 2]
    else:
        k0 = round(math.log(lay.gh / 7.4) / math.log(S_STEP))
        ks = range(k0 - 16, k0 + 17, 4)
    fit = _fit(font, lay.V, pens, right, ink_right, lay.cy, ks, blur)
    if not fit:
        return None
    total, scores, k, tx, ty = fit
    best, lead = scores.max(axis=1), np.sort(scores, axis=1)
    lead = lead[:, -1] - lead[:, -2]
    digits = "".join(DIGITS[i] for i in scores.argmax(axis=1))
    exp_s, pct_s = digits[:n_exp], digits[n_exp:]
    ok = (best.min() >= MIN_SCORE and lead.min() >= MIN_LEAD
          and not (len(exp_s) > 1 and exp_s[0] == "0") and not (len(pct_s) > 3 and pct_s[0] == "0"))
    line = label = 0.0
    if ok or info is not None:
        real = ("{:,}".format(int(exp_s)) + " " if exp_s else "") + "[" + pct_s[:-2] + "." + pct_s[-2:] + "%]"
        if len(real) == len(text):                    # (another digit count would move everything)
            line = _line_score(font, lay.V, real, k, tx, ty, blur)
        label = _label_score(font, lay.V, k, tx, ty, blur) if n_exp else _open_score(font, lay.V, k, tx, ty, blur)
    if info is not None:
        info.clear()
        info.update(digits=digits, best=best, lead=lead, line=line, label=label, blur=blur,
                    scale=S_STEP ** k, tx=tx, ty=ty)
    if not ok or line < MIN_LINE or label < (MIN_LABEL if n_exp else MIN_OPEN):
        return None
    return (int(exp_s) if exp_s else None), int(pct_s) / 100


def read_layout_v2(font, lay, info=None):
    """(exp, pct) read by drawing the game's font, (None, pct) on a percentage-only bar, or None if anything
    is unclear. Same answers as maple_exp.read_layout. `info` (a dict) gets the scores, for tuning.
    If the exact font doesn't match, it tries again with a little extra smoothing (a picture that was
    resized or compressed on the way to us); the same checks apply."""
    exp_cells, pct_cells = lay.exp, _pct_cells(lay)
    if any(c[2] != "digit" for c in exp_cells + pct_cells):
        return None
    if not 3 <= len(pct_cells) <= 5 or len(exp_cells) > MAX_EXP_DIGITS:
        return None
    for blur in BLURS:
        got = _read(font, lay, blur, info)
        if got:
            return got
    return None

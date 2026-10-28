import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from difflib import SequenceMatcher
from pathlib import Path
from tkinter import font as tkfont, simpledialog

FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
BUNDLE = Path(getattr(sys, "_MEIPASS", HERE))
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
os.environ["MAPLE_EXP_DATA"] = str(DATA)
if not FROZEN:
    sys.path.insert(0, str(HERE / "engine"))
    sys.path.insert(0, str(HERE))
if not (HERE / "potki.json").exists() and (BUNDLE / "potki.json").exists():
    import shutil
    shutil.copyfile(BUNDLE / "potki.json", HERE / "potki.json")

import mss  # noqa: E402
import mss.tools  # noqa: E402

import maple_exp as m  # noqa: E402
import hpmp  # noqa: E402
from capture import ScreenCapture, grab  # noqa: E402
from mesocount import MesoCounter  # noqa: E402
from potcount import PotCounter, amount  # noqa: E402


def _no_network(*a, **k):
    raise OSError("MapleHUD: siec wylaczona")


m.urllib.request.urlopen = _no_network
m.webbrowser.open = lambda *a, **k: False

CONFIG = DATA / "config.json"
POTKI = HERE / "potki.json"
POLL = 1.5
HPMP_POLL = 0.25
SESJA = DATA / "sesja.log"
MAPY = DATA / "mapy.csv"
MIN_MAP_ROW = 120
SUMMARY_EVERY = 30
UI_HALF = 400

HEAD_TOP, HEAD_BOT = "#ffd98a", "#f29b38"
HEAD_TEXT = "#5b2a07"
BODY = "#fff4df"
CARD = "#fffbf2"
BORDER = "#d9a45a"
TEXT = "#3b2a1c"
LABEL = "#9b7a52"
ORANGE = "#e8771a"
GOLD = "#b88400"
GREEN = "#3c9a35"
RED = "#d6453a"
BLUE = "#3577d4"
PURPLE = "#9b4fd0"
BAR_A, BAR_B = "#e3ee6a", "#a9c92a"

STATUS_PL = (
    ("MapleStory window not found", "Nie widzę okna MapleStory. Gra włączona?"),
    ("MapleStory is minimized", "Gra jest zminimalizowana."),
    ("Can't find the EXP bar", "Nie widzę paska EXP na dole gry. Coś go zasłania?"),
    ("covering the inventory's mesos", "Overlay zasłania meso w ekwipunku – przesuń eq."),
    ("covering the EXP", "Overlay zasłania pasek EXP."),
    ("Storage window open", "Otwarty storage – zmiany meso pomijane."),
    ("NPC shop window open", "Otwarty sklep – zmiany meso pomijane."),
    ("Trade window open", "Otwarty trade – zmiany meso pomijane."),
    ("Mesos can't be read", "Nie mogę odczytać meso."),
)
STATUS_DROP = ("Tesseract", "Map names", "class", "party list", "Telling characters", "README", "minimap",
               "potion bar")


def status_pl(text):
    out = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text or ""):
        hit = next((pl for en, pl in STATUS_PL if en in part), None)
        if hit:
            out.append(hit)
        elif part and not any(d in part for d in STATUS_DROP):
            out.append(part)
    return " ".join(dict.fromkeys(out))


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fmt(n):
    if n is None:
        return "—"
    a = abs(n)
    s = "-" if n < 0 else ""
    if a >= 1e9:
        return f"{s}{a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{s}{a / 1e6:.2f}M"
    if a >= 1e4:
        return f"{s}{a / 1e3:.1f}K"
    return f"{s}{a:,.0f}"


def fmt_time(sec):
    if sec is None or sec < 0 or sec > 999 * 3600:
        return "—"
    h, r = divmod(int(sec), 3600)
    return f"{h}h {r // 60:02d}m" if h else f"{r // 60}m {r % 60:02d}s"


def fmt_clock(sec):
    h, r = divmod(int(sec), 3600)
    return f"{h}:{r // 60:02d}:{r % 60:02d}"


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def rrect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


class Potki:
    def __init__(self):
        table = load_json(m.ASSETS / "potion_table.json", {"items": []})
        self.npc = {i["name"]: i for i in table["items"]}
        cfg = load_json(POTKI, {})
        self.items = {k: v for k, v in (cfg.get("potki") or {}).items() if isinstance(v, dict)}
        self.in_use = [n for n in cfg.get("uzywane") or [] if isinstance(n, str)]
        num = lambda k, d: cfg.get(k) if isinstance(cfg.get(k), (int, float)) else d
        self.down, self.up = num("tolerancja_spadek", 45), num("tolerancja_regen", 15)

    def price(self, name):
        p = self.items.get(name, {}).get("cena")
        if isinstance(p, (int, float)) and p >= 0:
            return p
        return self.npc.get(name, {}).get("price", 0) or 0

    def stats(self, name):
        it = self.items.get(name, {})
        return it.get("hp"), it.get("mp")

    def counter(self):
        pots = []
        for n in self.in_use:
            hp, mp = self.stats(n)
            pots.append(dict(name=n, hp=hp, mp=mp))
        return PotCounter(pots, self.down, self.up)


class HudReader(m.ScreenReader):
    own_rects = ()

    def _hide_own(self, shot, screen_copy=False):
        if not shot or (self.capture.sees_through_windows and not screen_copy):
            return shot
        img, sx, sy = shot
        copied = False
        for r in self.own_rects:
            x0, y0 = max(0, r[0] - sx), max(0, r[1] - sy)
            x1, y1 = min(img.shape[1], r[0] + r[2] - sx), min(img.shape[0], r[1] + r[3] - sy)
            if x0 < x1 and y0 < y1:
                if not copied:
                    img, copied = img.copy(), True
                img[y0:y1, x0:x1] = 0
        return img, sx, sy

    def _covered(self, x, y, w, h, margin=0):
        return any(x - margin < r[0] + r[2] and r[0] < x + w + margin and y - margin < r[1] + r[3]
                   and r[1] < y + h + margin for r in self.own_rects)


class Engine:
    def __init__(self, cfg, potki):
        self.cfg = cfg
        self.reader = HudReader(m.DigitTemplates.load())
        self.reader.next_bar = float("inf")
        self.reader.saved_v2 = dict(cfg.get("exp_v2_spots") or {})
        saved = cfg.get("mesos_box")
        if isinstance(saved, list) and len(saved) == 6:
            self.reader.saved_mesos = tuple(saved)
        self.session = m.Session(cfg.get("gap_seconds", 15))
        self.t = self.session.exp
        self.meso = MesoCounter()
        self.map_cur, self.map_cand, self.seg = None, None, None
        self.set_counter(potki)
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.status = "Szukam gry..."
        self.error = True
        self.rejected = 0
        self.level_up_at = self.died_at = None
        self.hpmp = None
        self.hpmp_at = 0.0
        self.ui_scale = None
        self.dirty_cfg = False
        self.potki_ref = potki
        self.last_mesos = self.last_window = self.last_map_read = None
        self.next_summary = time.monotonic() + SUMMARY_EVERY
        try:
            self._logf = open(SESJA, "a", encoding="utf-8", buffering=1)
        except Exception:
            self._logf = None
        self.log(f"=== start MapleHUD, liczone poty: {', '.join(potki.in_use)}, tolerancja -{potki.down}/+{potki.up}")
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._hpmp_worker, daemon=True).start()

    def log(self, msg):
        if self._logf:
            try:
                self._logf.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
            except Exception:
                pass

    def set_counter(self, potki, used=None):
        self.counter = potki.counter()
        self.counter.on_jump = self._on_jump
        if used:
            self.counter.used = used

    def _on_jump(self, base, reading, what):
        (hp0, hpm0), (mp0, mpm0) = base
        (hp, hpm), (mp, mpm) = reading
        self.log(f"HP {hp0}->{hp}/{hpm} ({hp - hp0:+})  MP {mp0}->{mp}/{mpm} ({mp - mp0:+})  => {what}")

    def _summary(self, potki):
        s = self.snapshot(potki)
        used = ", ".join(f"{n} x{c}" for n, c in self.counter.used.items() if c) or "brak"
        self.log(f"[co {SUMMARY_EVERY}s] czas {fmt_clock(s['elapsed'])}, stan {s['state']}, EXP {s['exp']} "
                 f"EXP/h {fmt(s['exp_h'])}, meso w eq {self.meso.base}, zarobione {self.meso.gained}, "
                 f"meso/h {fmt(s['meso_h'])}, poty: {used}, koszt {fmt(s['cost'])}, "
                 f"HP/MP {s['hpmp']}, status: {s['status'] or '-'}")

    def game_rect(self):
        hwnd = self.reader.hwnd
        if not hwnd:
            return None
        try:
            return m.PLATFORM.client_rect(hwnd)
        except Exception:
            return None

    def _worker(self):
        while not self.stop.is_set():
            try:
                with mss.mss() as sct:
                    cap = ScreenCapture(sct)
                    while not self.stop.is_set():
                        t0 = time.monotonic()
                        try:
                            self.q.put(("r", self.reader.read(cap), t0))
                        except Exception as e:
                            m.log_error("reading the screen", e)
                            self.q.put(("e", f"{type(e).__name__}: {e}", t0))
                        self.stop.wait(max(0.1, POLL - (time.monotonic() - t0)))
            except Exception as e:
                m.log_error("starting to read the screen", e)
                self.stop.wait(5)

    def _hpmp_worker(self):
        while not self.stop.is_set():
            try:
                with mss.mss() as sct:
                    while not self.stop.is_set():
                        t0 = time.monotonic()
                        rect = self.game_rect()
                        if rect:
                            r = self._read_hpmp(sct, rect)
                            if r:
                                self.q.put(("hp", r, t0))
                        self.stop.wait(max(0.05, HPMP_POLL - (time.monotonic() - t0)))
            except Exception as e:
                m.log_error("reading hp/mp", e)
                self.stop.wait(2)

    def _read_hpmp(self, sct, rect):
        wx, wy, ww, wh = rect
        full = wh / 768
        half = int((UI_HALF + 20) * full)
        tall = int(40 * full)
        shot = grab(sct, wx + ww // 2 - half, wy + wh - tall, 2 * half, tall)
        if not shot:
            return None
        img = shot[0]
        fields = hpmp.find_fields(img)
        if len(fields) < 2:
            return None
        fh = (fields[0][3] - fields[0][1]) / 7
        scale = min((full, 1.0), key=lambda s: abs(s - fh))
        self.ui_scale = scale
        hp = hpmp.parse(hpmp.read_field(img, fields[0], scale))
        mp = hpmp.parse(hpmp.read_field(img, fields[1], scale))
        return (hp, mp) if hp and mp else None

    def counting(self):
        s = self.session
        return s.on and self.t.exp is not None and not m.is_town(self.map_cur)

    def _start_segment(self):
        self.seg = dict(gained=self.t.gained, el=self.t.elapsed(), meso=self.meso.gained, used=dict(self.counter.used),
                        level=m.level_for_req(self.t.req) or self.cfg.get("level"))

    def _map_read(self, name):
        if not name:
            return
        if name != self.last_map_read:
            self.last_map_read = name
            self.log(f"minimapa: {name}")
        cur = self.map_cur
        if cur is None:
            self.map_cur = name
            self._start_segment()
            return
        a, b = name.lower(), cur.lower()
        if a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.75:
            self.map_cand = None
            return
        if self.map_cand and self.map_cand[0] == name:
            self.map_cand[1] += 1
        else:
            self.map_cand = [name, 1]
        if self.map_cand[1] < 3:
            self.reader.map_unread, self.reader.next_map_read = True, time.monotonic() + 1
        else:
            self.map_row()
            self.log(f"nowa mapa: {name}")
            self.map_cur, self.map_cand = name, None
            self._start_segment()

    def map_row(self):
        g, name = self.seg, self.map_cur
        if not g or not name:
            return
        el = self.t.elapsed() - g["el"]
        if el < MIN_MAP_ROW:
            return
        used = {n: c - g["used"].get(n, 0) for n, c in self.counter.used.items() if c - g["used"].get(n, 0) > 0}
        potki = self.potki_ref
        cost = sum(c * potki.price(n) for n, c in used.items())
        exp_h = (self.t.gained - g["gained"]) / el * 3600
        meso_h = (self.meso.gained - g["meso"]) / el * 3600 if self.meso.base is not None else None
        cost_h = cost / el * 3600
        net_h = (meso_h or 0) - cost_h
        used_txt = " ".join(f"{n}x{c}" for n, c in used.items())
        new = not MAPY.exists()
        try:
            with open(MAPY, "a", encoding="utf-8") as f:
                if new:
                    f.write("data;mapa;lv;minuty;exp_h;meso_h;koszt_potow_h;netto_h;poty\n")
                vals = [time.strftime("%Y-%m-%d %H:%M"), name, g["level"] or "", round(el / 60, 1), round(exp_h),
                        "" if meso_h is None else round(meso_h), round(cost_h), round(net_h), used_txt]
                f.write(";".join(str(v) for v in vals) + "\n")
        except Exception as e:
            m.log_error("writing mapy.csv", e)
        self.log(f"MAPA {name}: {fmt_clock(el)}, EXP/h {fmt(exp_h)}, meso/h {fmt(meso_h)}, poty/h {fmt(cost_h)}, "
                 f"netto/h {fmt(net_h)}, poty: {used_txt or 'brak'}")

    def pump(self):
        while True:
            try:
                kind, r, at = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "e":
                self.status, self.error = r, True
            elif kind == "hp":
                self.hpmp, self.hpmp_at = r, at
                self.counter.feed(r, self.counting(), at)
            else:
                self._handle(r)
        self.session.tick(time.monotonic())
        if time.monotonic() >= self.next_summary and self.potki_ref:
            self.next_summary = time.monotonic() + SUMMARY_EVERY
            self._summary(self.potki_ref)

    def _handle(self, r):
        s, t, now = self.session, self.t, time.monotonic()
        if r.mesos_at:
            self.cfg["mesos_box"] = list(r.mesos_at)
            self.reader.saved_mesos = tuple(r.mesos_at)
            self.dirty_cfg = True
        if r.v2_at:
            key, box = r.v2_at
            spots = dict(self.cfg.get("exp_v2_spots") or {})
            spots[key] = list(box)
            self.cfg["exp_v2_spots"] = dict(list(spots.items())[-8:])
            self.reader.saved_v2 = dict(self.cfg["exp_v2_spots"])
            self.dirty_cfg = True
        if r.window != self.last_window:
            self.last_window = r.window
            if r.window:
                self.log(f"okno: {r.window} (zmiany meso pomijane)")
        if r.mesos is not None and r.mesos != self.last_mesos:
            self.log(f"meso w eq: {self.last_mesos} -> {r.mesos}  (EXP leci: {t.running})")
            self.last_mesos = r.mesos
        if r.window:
            self.meso.note_window(now)
        if r.mesos is not None:
            got = self.meso.feed(r.mesos, r.window, s.on and t.exp is not None, now)
            if got:
                self.log(f"meso +{got:,} (zarobione w sesji: {self.meso.gained:,})")
        if r.map:
            self._map_read(m.snap_map_name(r.map))
        self.error = not r.candidates
        if r.candidates:
            if r.percent_only:
                level, source = r.level or ((self.cfg["level"], "typed") if self.cfg.get("level") else (None, None))
                ok, note = s.observe_percent(r.candidates[0][1], level, source, now)
            else:
                ok, note = s.observe(r.candidates, r.confident, now)
            self.rejected = 0 if ok else self.rejected + 1
            if self.rejected >= 10:
                self.reader.box, self.rejected = None, 0
            if note == "LEVEL UP!":
                self.level_up_at = now
            elif note == "died":
                self.died_at = now
            status = r.note or ""
            if note == "waiting to read your level":
                status = "Pasek pokazuje tylko %. PPM > Ustaw poziom."
        else:
            status = " ".join(x for x in (r.where, r.note) if x)
        self.status = status_pl(status)

    def toggle(self):
        if self.session.on:
            self.session.pause()
        else:
            self.session.start(time.monotonic())

    def reset(self):
        on = self.session.on
        self.session.reset()
        self.counter.reset()
        self.meso.gained = 0
        self.reader.look_again()
        if on:
            self.session.start(time.monotonic())
        self._start_segment()

    def snapshot(self, potki):
        t, s = self.t, self.session
        now = time.monotonic()
        el = t.elapsed()
        rate = t.rate()
        level = m.level_for_req(t.req) or self.cfg.get("level")
        pct = (t.exp / t.req * 100) if t.exp is not None and t.req else t.pct
        ttl = (t.req - t.exp) / rate * 3600 if rate and t.req and t.exp is not None else None
        meso_h = self.meso.gained / el * 3600 if el >= 30 and self.meso.base is not None else None
        used = self.counter.used
        cost = sum(n * potki.price(name) for name, n in used.items())
        cost_h = cost / el * 3600 if el >= 30 else None
        net_h = (meso_h or 0) - (cost_h or 0) if meso_h is not None or cost_h else None
        rows, hp_h, mp_h = [], 0.0, 0.0
        hpm = self.hpmp[0][1] if self.hpmp else 0
        mpm = self.hpmp[1][1] if self.hpmp else 0
        for name in list(dict.fromkeys(potki.in_use + list(used))):
            n = used.get(name, 0)
            per_h = n / el * 3600 if el >= 30 else None
            hp, mp = potki.stats(name)
            if per_h:
                hp_h += amount(hp, hpm) * per_h
                mp_h += amount(mp, mpm) * per_h
            rows.append(dict(name=name, used=n, per_h=per_h, cost=n * potki.price(name), hp=hp, mp=mp,
                             price=potki.price(name)))
        state = "on" if t.running else "wait" if s.on else "off"
        if t.exp is None:
            state = "wait"
        if self.error and not t.running:
            state = "err"
        flash = None
        if self.level_up_at and now - self.level_up_at < 8:
            flash = "LEVEL UP!"
        elif self.died_at and now - self.died_at < 8:
            flash = "Śmierć – strata EXP nie liczy się do EXP/h."
        last = self.counter.events[-1] if self.counter.events else None
        return dict(map=self.map_cur, state=state, elapsed=el, level=level, pct=pct, exp=t.exp, ttl=ttl, exp_h=rate,
                    exp_5=t.rolling_rate(), meso_h=meso_h, meso_seen=self.meso.base is not None, cost=cost,
                    cost_h=cost_h, net_h=net_h, rows=rows, hp_h=hp_h, mp_h=mp_h, status=flash or self.status,
                    flash=bool(flash), estimated=t.estimated, waiting=s.waiting, on=s.on,
                    hpmp=self.hpmp if now - self.hpmp_at < 3 else None, counting=self.counting(),
                    last=(now - last[0], last[1]) if last else None)


def demo_snapshot():
    return dict(map="Henesys Hunting Ground I", state="on", elapsed=2712, level=27, pct=14.77, exp=9406, ttl=4980, exp_h=44178, exp_5=46100,
                meso_h=312400, meso_seen=True, cost=7350, cost_h=9757, net_h=302643, rows=[
                    dict(name="Red Potion", used=41, per_h=54.4, cost=2050, hp=100, mp=0, price=50),
                    dict(name="Meat", used=12, per_h=15.9, cost=960, hp=160, mp=0, price=80),
                    dict(name="Lemon", used=19, per_h=25.2, cost=2850, hp=0, mp=150, price=150),
                    dict(name="Blue Potion", used=0, per_h=0, cost=0, hp=0, mp=200, price=220)],
                hp_h=7950, mp_h=3720, status="", flash=False, estimated=False, waiting=None, on=True,
                hpmp=((612, 829), (431, 657)), counting=True, last=(3.2, ["Red Potion"]))


class Panel:
    def __init__(self, hud, master, side):
        self.hud, self.side = hud, side
        self.win = master if side == "left" else tk.Toplevel(master)
        w = self.win
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", hud.cfg.get("alpha", 0.95))
        w.configure(bg=BODY)
        self.c = tk.Canvas(w, width=10, height=10, bg=BODY, highlightthickness=0, bd=0)
        self.c.pack()
        self.size = None
        self.c.bind("<Button-3>", hud.menu_at)
        for tag, fn in (("b_toggle", hud.toggle), ("b_reset", hud.reset), ("b_more", hud.toggle_details),
                        ("b_close", hud.close), ("body", hud.toggle_details)):
            self.c.tag_bind(tag, "<ButtonRelease-1>", lambda e, f=fn: f())
            if tag != "body":
                self.c.tag_bind(tag, "<Enter>", lambda e: self.c.config(cursor="hand2"))
                self.c.tag_bind(tag, "<Leave>", lambda e: self.c.config(cursor=""))

    def place(self, x, y, w, h):
        if self.size != (w, h):
            self.size = (w, h)
            self.c.config(width=w, height=h)
        g = f"{w}x{h}+{x}+{y}"
        if self.win.geometry() != g:
            self.win.geometry(g)

    def rect(self):
        try:
            return m.PLATFORM.own_window_rect(self.win)
        except Exception:
            return None


def font_px(name, px):
    return (name, -max(7, round(px)))


class HUD:
    def __init__(self, root, demo=False):
        self.root, self.demo = root, demo
        self.cfg = {"alpha": 0.95, "gap_seconds": 15, "level": None, **load_json(CONFIG, {})}
        self.potki = Potki()
        self.engine = None if demo else Engine(self.cfg, self.potki)
        if self.engine:
            self.engine.potki_ref = self.potki
        if self.engine:
            self.engine.session.start(time.monotonic())
        self._fonts()
        root.title("MapleHUD")
        try:
            root.iconbitmap(default=str(BUNDLE / "MapleHUD.ico"))
        except Exception:
            pass
        self.left = Panel(self, root, "left")
        self.right = Panel(self, root, "right")
        self.details = Panel(self, root, "details")
        self.details.win.withdraw()
        self.show_details = False
        self.visible = True
        self.scale = 1.0
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="MapleHUD © 2026 tesem", state="disabled")
        self.menu.add_separator()
        self.menu.add_command(label="Start / Pauza", command=self.toggle)
        self.menu.add_command(label="Reset sesji", command=self.reset)
        self.menu.add_command(label="Szczegóły potów", command=self.toggle_details)
        self.menu.add_separator()
        self.menu.add_command(label="Edytuj potki.json (ceny, HP/MP, używane)", command=lambda: os.startfile(POTKI))
        self.menu.add_command(label="Wczytaj potki.json", command=self.reload_potki)
        self.menu.add_command(label="Ustaw poziom (gdy pasek ma tylko %)", command=self.set_level)
        self.menu.add_command(label="Przezroczystość", command=self.set_alpha)
        self.menu.add_separator()
        self.menu.add_command(label="Zamknij", command=self.close)
        self._tick()

    def _fonts(self):
        fams = set(tkfont.families())
        if "Manrope" not in fams and m.PLATFORM.register_fonts([m.ASSETS / "fonts" / n for n in m.FONT_FILES]):
            fams = set(tkfont.families(self.root))
        ok = "Manrope" in fams
        self.fam = (dict(reg="Manrope", semi="Manrope SemiBold", bold="Manrope Bold", xbold="Manrope ExtraBold")
                    if ok else dict(reg="Segoe UI", semi="Segoe UI Semibold", bold="Segoe UI Semibold",
                                    xbold="Segoe UI Black"))

    def f(self, kind, px):
        return font_px(self.fam[kind], px * self.scale)

    def _game_in_front(self):
        if self.demo:
            return True
        hwnd = self.engine.reader.hwnd
        if not hwnd:
            return True
        if not self.engine.game_rect():
            return False
        u = ctypes.windll.user32
        fg = u.GetForegroundWindow()
        if fg == hwnd:
            return True
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        return pid.value == os.getpid()

    def _set_visible(self, vis):
        if vis == self.visible:
            return
        self.visible = vis
        for p in (self.left, self.right) + ((self.details,) if self.show_details else ()):
            if vis:
                p.win.deiconify()
                p.win.attributes("-topmost", True)
            else:
                p.win.withdraw()

    def _tick(self):
        try:
            self._set_visible(self._game_in_front())
            if self.engine:
                self.engine.pump()
                if self.engine.dirty_cfg:
                    self.save()
                    self.engine.dirty_cfg = False
                snap = self.engine.snapshot(self.potki)
            else:
                snap = demo_snapshot()
            self.layout()
            self.draw_left(snap)
            self.draw_right(snap)
            if self.show_details:
                self.draw_details(snap)
            if self.engine:
                rects = [p.rect() for p in (self.left, self.right) + ((self.details,) if self.show_details else ())]
                self.engine.reader.own_rects = tuple(r for r in rects if r)
                self.engine.reader.own_rect = self.engine.reader.own_rects[0] if self.engine.reader.own_rects else None
        except Exception as e:
            m.log_error("hud tick", e)
        self.root.after(250, self._tick)

    def game_rect(self):
        if self.demo:
            return self.cfg.get("demo_rect")
        return self.engine.game_rect()

    def layout(self):
        rect = self.game_rect()
        if rect:
            wx, wy, ww, wh = rect
            ui = (self.engine.ui_scale if self.engine and self.engine.ui_scale else None) or wh / 768
        else:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            wx, wy, ww, wh, ui = 0, 0, sw, sh, 1.0
        s = self.scale = max(0.8, min(2.5, ui))
        m_ = round(6 * s)
        zone = ww / 2 - UI_HALF * ui
        pw = int(min(zone - 2 * m_, 330 * s))
        ph = round(64 * s)
        if pw < 190 * s:
            pw = int(min(300 * s, ww / 2 - 2 * m_))
            y = wy + wh - round(72 * ui) - ph - m_
            lx, rx = wx + m_, wx + ww - m_ - pw
        else:
            y = wy + wh - ph - round(3 * s)
            lx = int(wx + zone - m_ - pw)
            rx = int(wx + ww - zone + m_)
        self.left.place(lx, y, pw, ph)
        self.right.place(rx, y, pw, ph)
        self.geom = (rx, y, pw, ph)

    def header(self, c, w, hh, title, dot=None):
        for i in range(hh):
            c.create_line(0, i, w, i, fill=mix(HEAD_TOP, HEAD_BOT, i / max(1, hh - 1)))
        x = round(7 * self.scale)
        if dot:
            r = 3.5 * self.scale
            c.create_oval(x, hh / 2 - r, x + 2 * r, hh / 2 + r, fill=dot, outline="#ffffff")
            x += round(11 * self.scale)
        c.create_text(x, hh / 2, text=title, font=self.f("xbold", 10), fill=HEAD_TEXT, anchor="w")

    def buttons(self, c, w, hh, items):
        s = self.scale
        x = w - round(4 * s)
        size = hh - round(4 * s)
        for tag, sym in items:
            rrect(c, x - size, round(2 * s), x, round(2 * s) + size, round(4 * s), fill="#fff3dc", outline="#d48a35",
                  tags=tag)
            c.create_text(x - size / 2, hh / 2, text=sym, font=font_px("Segoe UI Symbol", 9 * s), fill=HEAD_TEXT,
                          tags=tag)
            x -= size + round(3 * s)
        return x

    def columns(self, c, w, top, cols):
        s = self.scale
        n = len(cols)
        cw = w / n
        for i, (lab, val, col) in enumerate(cols):
            x = i * cw + round(8 * s)
            if i:
                c.create_line(i * cw, top + 6 * s, i * cw, top + 40 * s, fill=mix(BODY, BORDER, 0.6))
            c.create_text(x, top + 11 * s, text=lab, font=self.f("semi", 8), fill=LABEL, anchor="w", tags="body")
            size = 15 if len(val) <= 7 else 12
            c.create_text(x, top + 29 * s, text=val, font=self.f("bold", size), fill=col, anchor="w", tags="body")

    def draw_left(self, s):
        c = self.left.c
        w, h = self.left.size
        sc = self.scale
        c.delete("all")
        hh = round(18 * sc)
        dot = {"on": GREEN, "wait": "#f2b33a", "off": "#9a9a9a", "err": RED}[s["state"]]
        title = f"LV {s['level'] or '?'}" + (f"  ·  {s['map']}" if s.get("map") else "")
        self.header(c, w, hh, title if len(title) <= 34 else title[:33] + "…", dot)
        x = self.buttons(c, w, hh, (("b_reset", "⟲"), ("b_toggle", "⏸" if s["on"] else "▶")))
        c.create_text(x - 4 * sc, hh / 2, text=fmt_clock(s["elapsed"]), font=self.f("semi", 8.5), fill=HEAD_TEXT,
                      anchor="e")
        if s["pct"] is not None:
            fx = w * min(100, s["pct"]) / 100
            for i in range(round(3 * sc)):
                c.create_line(0, hh + i, fx, hh + i, fill=mix(BAR_A, BAR_B, i / 3))
        if s["exp"] is None and s["status"]:
            c.create_text(round(8 * sc), hh + 6 * sc, text=s["status"], font=self.f("reg", 8.5), fill=LABEL,
                          anchor="nw", width=w - 16 * sc, tags="body")
        else:
            pct = "" if s["pct"] is None else f" ({s['pct']:.1f}%)"
            nxt = (f"DO LV {s['level'] + 1}" if s["level"] else "DO LVL") + pct
            self.columns(c, w, hh, (("EXP / H", fmt(s["exp_h"]), ORANGE), ("OST. 5 MIN", fmt(s["exp_5"]), TEXT),
                                    (nxt, fmt_time(s["ttl"]), TEXT)))
        c.create_rectangle(0, 0, w - 1, h - 1, outline=BORDER)

    def draw_right(self, s):
        c = self.right.c
        w, h = self.right.size
        sc = self.scale
        c.delete("all")
        hh = round(18 * sc)
        self.header(c, w, hh, "MESO")
        x = self.buttons(c, w, hh, (("b_close", "✕"), ("b_more", "▴" if not self.show_details else "▾")))
        if s["hpmp"]:
            (hp, hpm), (mp, mpm) = s["hpmp"]
            info = f"poty −{fmt(s['cost'])}"
            col = HEAD_TEXT
        else:
            info, col = "nie widzę HP/MP", RED
        c.create_text(x - 4 * sc, hh / 2, text=info, font=self.f("semi", 8.5), fill=col, anchor="e")
        net = s["net_h"]
        meso = fmt(s["meso_h"]) if s["meso_seen"] else "otwórz eq"
        self.columns(c, w, hh, (("MESO / H", meso, GOLD),
                                ("POTY / H", "-" + fmt(s["cost_h"]) if s["cost_h"] else "0", RED),
                                ("NETTO / H", fmt(net), GREEN if net is None or net >= 0 else RED)))
        c.create_rectangle(0, 0, w - 1, h - 1, outline=BORDER)

    def draw_details(self, s):
        p, c, sc = self.details, self.details.c, self.scale
        w = self.geom[2]
        rows = [r for r in s["rows"] if r["used"] or r["name"] in self.potki.in_use]
        rh = round(30 * sc)
        msgs = []
        if s["status"]:
            msgs.append(s["status"])
        if not s["hpmp"]:
            msgs.append("Nie widzę HP/MP na pasku – poty nie są liczone.")
        elif not s["counting"]:
            msgs.append("Poty liczone dopiero gdy idzie EXP.")
        if s["last"]:
            ago, names = s["last"]
            msgs.append(f"Ostatnio: {' + '.join(names)} ({fmt_time(ago)} temu)")
        hh = round(18 * sc)
        c.delete("all")
        y = hh + round(18 * sc)
        y_rows = y
        y += len(rows) * (rh + round(3 * sc))
        tid = c.create_text(round(9 * sc), y + 4 * sc, text="\n".join(msgs), font=self.f("reg", 8), fill=LABEL,
                            anchor="nw", width=w - 18 * sc)
        bb = c.bbox(tid)
        h = int((bb[3] if bb and msgs else y) + 8 * sc)
        self.header(c, w, hh, "POTY")
        hpmp_txt = ""
        if s["hpmp"]:
            (hp, hpm), (mp, mpm) = s["hpmp"]
            hpmp_txt = f"HP {hp}/{hpm} · MP {mp}/{mpm}"
        c.create_text(w - 8 * sc, hh / 2, text=hpmp_txt, font=self.f("semi", 8), fill=HEAD_TEXT, anchor="e")
        cx_used, cx_h = w * 0.58, w * 0.76
        c.create_text(cx_used, hh + 9 * sc, text="UŻYTE", font=self.f("semi", 7.5), fill=LABEL, anchor="e")
        c.create_text(cx_h, hh + 9 * sc, text="NA H", font=self.f("semi", 7.5), fill=LABEL, anchor="e")
        c.create_text(w - 10 * sc, hh + 9 * sc, text="KOSZT", font=self.f("semi", 7.5), fill=LABEL, anchor="e")
        y = y_rows
        for r in rows:
            hp, mp = r["hp"], r["mp"]
            col = PURPLE if hp and mp else RED if hp else BLUE if mp else ORANGE
            rrect(c, 6 * sc, y, w - 6 * sc, y + rh, round(6 * sc), fill=CARD, outline=mix(BODY, BORDER, 0.7))
            c.create_oval(12 * sc, y + 7 * sc, 20 * sc, y + 15 * sc, fill=col, outline="")
            c.create_text(26 * sc, y + 11 * sc, text=r["name"], font=self.f("semi", 9), fill=TEXT, anchor="w")
            info = " · ".join(x for x in (f"{hp} HP" if hp else "", f"{mp} MP" if mp else "",
                                          f"{fmt(r['price'])} meso") if x)
            c.create_text(26 * sc, y + 22 * sc, text=info, font=self.f("reg", 7.5), fill=LABEL, anchor="w")
            c.create_text(cx_used, y + rh / 2, text=f"×{r['used']}", font=self.f("semi", 9), fill=TEXT, anchor="e")
            c.create_text(cx_h, y + rh / 2, text=fmt(r["per_h"]) if r["per_h"] else "—", font=self.f("semi", 9),
                          fill=TEXT, anchor="e")
            c.create_text(w - 12 * sc, y + rh / 2, text=("-" + fmt(r["cost"])) if r["cost"] else "0",
                          font=self.f("semi", 9), fill=RED if r["cost"] else LABEL, anchor="e")
            y += rh + round(3 * sc)
        c.create_rectangle(0, 0, w - 1, h - 1, outline=BORDER)
        rx, ry, pw, ph = self.geom
        p.place(rx, ry - h - round(4 * sc), w, h)
        c.tag_raise("all")

    def toggle_details(self):
        self.show_details = not self.show_details
        if self.show_details:
            self.details.win.deiconify()
            self.details.win.attributes("-topmost", True)
        else:
            self.details.win.withdraw()

    def menu_at(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def toggle(self):
        if self.engine:
            self.engine.toggle()

    def reset(self):
        if self.engine:
            self.engine.reset()

    def reload_potki(self):
        self.potki = Potki()
        if self.engine:
            used = self.engine.counter.used
            self.engine.set_counter(self.potki, used)
            self.engine.potki_ref = self.potki

    def set_level(self):
        v = simpledialog.askinteger("Poziom", "Twój poziom (jak w grze):", parent=self.root, minvalue=1,
                                    maxvalue=len(m.EXP_TABLE), initialvalue=self.cfg.get("level") or None)
        if v:
            self.cfg["level"] = v
            self.save()

    def set_alpha(self):
        v = simpledialog.askinteger("Przezroczystość", "Krycie w % (60-100):", parent=self.root, minvalue=60,
                                    maxvalue=100, initialvalue=int(self.cfg.get("alpha", 0.95) * 100))
        if v:
            self.cfg["alpha"] = v / 100
            for p in (self.left, self.right, self.details):
                p.win.attributes("-alpha", v / 100)
            self.save()

    def save(self):
        try:
            CONFIG.write_text(json.dumps(self.cfg, indent=1), encoding="utf-8")
        except Exception as e:
            m.log_error("saving config", e)

    def close(self):
        if self.engine:
            e = self.engine
            e.map_row()
            e._summary(self.potki)
            self.engine.log("=== koniec")
            self.engine.stop.set()
        self.save()
        self.root.destroy()


def snap_all(hud, out):
    hud.root.update()
    rect = hud.game_rect()
    if rect:
        x, y, w, h = rect
    else:
        rs = [p.rect() for p in (hud.left, hud.right, hud.details) if p.rect()]
        x = min(r[0] for r in rs) - 20
        y = min(r[1] for r in rs) - 20
        w = max(r[0] + r[2] for r in rs) - x + 20
        h = max(r[1] + r[3] for r in rs) - y + 20
    with mss.mss() as sct:
        img = sct.grab({"left": x, "top": y, "width": w, "height": h})
        mss.tools.to_png(img.rgb, img.size, output=out)


def main():
    demo = "--demo" in sys.argv
    if not demo and "--snap" not in sys.argv and not m.PLATFORM.claim_single_instance("MapleHUD", "MapleHUD"):
        return
    if not demo:
        try:
            tess, tessdata, m.tesseract_state, m.tesseract_why = m.locate_tesseract()
            if tess:
                m.TESS = m.ocr.Tesseract(tess, tessdata=tessdata or None)
                m.tesseract_ok = True
            else:
                from winocr import WinOcr
                m.TESS = WinOcr()
                m.tesseract_ok = True
        except Exception as e:
            m.log_error("looking for Tesseract", e)
    root = tk.Tk()
    hud = HUD(root, demo)
    if "--details" in sys.argv:
        hud.toggle_details()
    if "--snap" in sys.argv:
        i = sys.argv.index("--snap")
        out = sys.argv[i + 1]
        delay = int(float(sys.argv[i + 2]) * 1000) if len(sys.argv) > i + 2 and sys.argv[i + 2][0].isdigit() else 1500

        def snap():
            snap_all(hud, out)
            hud.close()
        root.after(delay, snap)
    root.mainloop()


if __name__ == "__main__":
    main()

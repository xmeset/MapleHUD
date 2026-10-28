from itertools import combinations_with_replacement

MAX_AT_ONCE = 2


def amount(value, maximum):
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().endswith("%"):
        try:
            return int(float(value.strip()[:-1]) / 100 * maximum)
        except ValueError:
            return 0
    return 0


class PotCounter:
    """Counts potions from jumps of HP/MP read off the status bar.

    A jump that matches one or two of the potions in use is counted; anything else (heals, chairs,
    level-ups) is not. Hits and skill costs landing in the same moment only make a jump smaller (up to
    `down`), regen only a little bigger (up to `up`).
    A reading is believed once seen twice in a row."""

    def __init__(self, potions, down=45, up=15):
        self.potions = [p for p in potions if p.get("hp") or p.get("mp")]
        self.down, self.up = down, up
        self.used = {}
        self.last = {"hp": None, "mp": None}
        self.events = []
        self.base = None
        self.pending, self.seen = None, 0
        self.on_jump = None

    def reset(self):
        self.used, self.events = {}, []
        self.base = None

    def feed(self, reading, counting, now=0.0):
        if reading != self.pending:
            self.pending, self.seen = reading, 1
            return []
        self.seen += 1
        if self.seen != 2:
            return []
        base, self.base = self.base, reading
        if base is None:
            return []
        (hp0, hpm0), (mp0, mpm0) = base
        (hp, hpm), (mp, mpm) = reading
        if hpm != hpm0 or mpm != mpm0 or hp0 == 0:
            if self.on_jump:
                self.on_jump(base, reading, "zmiana max HP/MP lub smierc – pomijam")
            return []
        dhp, dmp = hp - hp0, mp - mp0
        if dhp <= self.up and dmp <= self.up:
            return []
        combo = self._explain(dhp, hp == hpm, hpm, dmp, mp == mpm, mpm) if counting else None
        if self.on_jump:
            self.on_jump(base, reading, ("POT: " + " + ".join(p["name"] for p in combo)) if combo
                         else "nie rozpoznano" if counting else "nie licze (brak EXP / pauza)")
        if not combo:
            return []
        for p in combo:
            self.used[p["name"]] = self.used.get(p["name"], 0) + 1
            for k in ("hp", "mp"):
                if p.get(k):
                    self.last[k] = p["name"]
        names = [p["name"] for p in combo]
        self.events.append((now, names))
        del self.events[:-50]
        return names

    def _fits(self, delta, total, capped):
        if total == 0:
            return delta <= self.up, 0
        if capped:
            return total >= delta - self.up, max(0, delta - total)
        r = delta - total
        return -self.down <= r <= self.up, abs(r)

    def _explain(self, dhp, hp_cap, hpm, dmp, mp_cap, mpm):
        best, best_key = None, None
        order = {p["name"]: i for i, p in enumerate(self.potions)}
        for n in range(1, MAX_AT_ONCE + 1):
            for combo in combinations_with_replacement(self.potions, n):
                shp = sum(amount(p.get("hp"), hpm) for p in combo)
                smp = sum(amount(p.get("mp"), mpm) for p in combo)
                ok_h, r_h = self._fits(dhp, shp, hp_cap)
                ok_m, r_m = self._fits(dmp, smp, mp_cap)
                if not (ok_h and ok_m):
                    continue
                pref = sum(0 if p["name"] in self.last.values() else 1 for p in combo)
                key = (n, round((r_h + r_m) / self.up), pref, sum(order[p["name"]] for p in combo))
                if best_key is None or key < best_key:
                    best, best_key = combo, key
            if best:
                return best
        return None

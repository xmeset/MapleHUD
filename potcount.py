from itertools import combinations_with_replacement

MAX_AT_ONCE = 2
PAIR = 4.0
REGEN_EVERY = 10.0
REGEN_SLACK = 0.6
PET_PAIRS = 3


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
    `down`), regen only a little bigger (up to `up`). With `skill_heals`, HP rising while MP is spent
    is a healing skill (Final Strike, Heal), not a potion, unless that MP cost was seen before without
    HP going up (an attack skill, so a potion drunk while attacking still counts).
    The pet drinks in the same frame as the hit that set it off, so any rise up to its potion's full
    heal is the pet; other potions of that kind count only from the quickslot (`bar`). A pet rise
    that comes with a quickslot use (`bar_used`) was that item: when most pet rises do, the pet's
    potion sits on the quickslot and is counted there. Otherwise it is `pet`, the potion from the
    settings. The same HP rise again a whole number of regen ticks later is regen (a warrior's
    Improved HP Recovery), not the pet: it is learnt and skipped. Rises explained by a quickslot
    potion are never taken for regen.
    A reading is believed once seen twice in a row."""

    def __init__(self, potions, down=45, up=15, skill_heals=True, pet=None):
        self.potions = [p for p in potions if p.get("hp") or p.get("mp")]
        self.pet_default = {k: (pet or {}).get(k) for k in ("hp", "mp")}
        self.bar = {}
        self.down, self.up = down, up
        self.skill_heals = skill_heals
        self.regens = set()
        self.costs = {}
        self.used = {}
        self.last = {"hp": None, "mp": None}
        self.events = []
        self.base = None
        self.pending, self.seen = None, 0
        self.on_jump = None
        self.on_note = None
        self.reset()

    def reset(self):
        self.used, self.events = {}, []
        self.recent, self.drops, self.rises = [], [], []
        self.paired, self.alone, self.bank = {}, {"hp": 0, "mp": 0}, {}
        self.pet_mode = {"hp": None, "mp": None}
        self.base = None

    def pet_on_bar(self, k):
        cands = [n for n in self.paired if self._stat(n) == k]
        best = max(cands, key=lambda n: self.paired[n], default=None)
        if best and self.paired[best] >= PET_PAIRS and self.paired[best] >= 2 * self.alone[k]:
            return best
        return None

    def pet(self, k):
        return self.pet_on_bar(k) or self.pet_default[k]

    def set_pet(self, k, name, potion=None):
        if potion and all(p["name"] != potion["name"] for p in self.potions):
            self.potions.append(potion)
        old = self.pet_default[k]
        if name == old:
            return
        self._sync()
        for n in (old, name):
            if n:
                self.bank[n] = self.used.get(n, 0)
        self.pet_default[k], self.alone[k] = name, 0
        self.recent = [e for e in self.recent if e[1] != k]
        self._sync()

    def _stat(self, name):
        p = next((p for p in self.potions if p["name"] == name), {})
        return "hp" if p.get("hp") else "mp" if p.get("mp") else None

    def _sync(self):
        for k in ("hp", "mp"):
            on_bar = self.pet_on_bar(k)
            d = self.pet_default[k]
            if d and (self.alone[k] or d in self.used):
                self.used[d] = self.bank.get(d, 0) + (0 if on_bar else self.alone[k])
            mode = on_bar or d
            if mode != self.pet_mode[k]:
                if self.pet_mode[k] is not None and self.on_note:
                    self.on_note(f"pet pije {mode}" + (" (z quickslota)" if on_bar else " (z ustawien)"))
                self.pet_mode[k] = mode

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
        if dmp < 0 and dhp <= self.up and hp0 < hpm:
            self.costs[-dmp] = self.costs.get(-dmp, 0) + 1
        if dhp <= self.up and dmp <= self.up:
            return []
        if self.skill_heals and dhp > self.up and dmp < 0 and self.costs.get(-dmp, 0) < 2:
            if self.on_jump:
                self.on_jump(base, reading, "leczenie ze skilla – pomijam")
            return []
        hp_only = dhp > self.up and abs(dmp) <= self.up
        if hp_only and self._regen(dhp, now):
            if self.on_jump:
                self.on_jump(base, reading, f"regen ({dhp:+} co {REGEN_EVERY:.0f} s) – pomijam")
            return []
        combo = self._explain(dhp, hp == hpm, hpm, dmp, mp == mpm, mpm) if counting else None
        if counting and not combo:
            combo = self._explain(dhp, hp == hpm, hpm, dmp, mp == mpm, mpm, True)
        notes, pet_hp = self._pair(combo or [], now)
        if hp_only and not any(p["name"] in self.bar and p.get("hp") for p in combo or []):
            self.rises.append([now, dhp, pet_hp])
        if self.on_jump:
            self.on_jump(base, reading, ("POT: " + " + ".join(notes)) if combo
                         else "nie rozpoznano" if counting else "nie licze (brak EXP / pauza)")
        if not combo:
            return []
        names = [p["name"] for p in combo]
        for p in combo:
            if p["name"] not in (self.pet("hp"), self.pet("mp")):
                self.used[p["name"]] = self.used.get(p["name"], 0) + 1
            for k in ("hp", "mp"):
                if p.get(k):
                    self.last[k] = p["name"]
        self._sync()
        self.events.append((now, names))
        del self.events[:-50]
        return names

    def _pair(self, combo, now):
        self.drops = [d for d in self.drops if now - d[0] <= PAIR]
        self.recent = [e for e in self.recent if now - e[0] <= PAIR]
        notes, pet_hp = [], None
        for p in combo:
            name, k = p["name"], self._stat(p["name"])
            if name == self.pet(k):
                d = next((d for d in self.drops if d[1] == k), None)
                if d:
                    self.drops.remove(d)
                    self.paired[d[2]] = self.paired.get(d[2], 0) + 1
                    notes.append(f"pet ({d[2]} z quickslota)")
                else:
                    self.alone[k] += 1
                    self.recent.append([now, k, "pet", name])
                    pet_hp = name if k == "hp" else pet_hp
                    notes.append(f"pet ({name})")
            elif name in self.bar:
                d = next((d for d in self.drops if d[2] == name), None)
                if d:
                    self.drops.remove(d)
                else:
                    self.recent.append([now, k, "bar", name])
                notes.append(name)
            else:
                notes.append(name)
        return notes, pet_hp

    def bar_used(self, name, now):
        k = self._stat(name)
        if not k:
            return None
        self.recent = [e for e in self.recent if now - e[0] <= PAIR]
        e = next((e for e in self.recent if e[2] == "bar" and e[3] == name), None) or \
            next((e for e in self.recent if e[2] == "pet" and e[1] == k), None)
        if not e:
            self.drops.append((now, k, name))
            return None
        self.recent.remove(e)
        if e[2] != "pet":
            return None
        for r in self.rises:
            if r[0] == e[0]:
                r[2] = None
        self.alone[k] = max(0, self.alone[k] - 1)
        self.paired[name] = self.paired.get(name, 0) + 1
        self._sync()
        return e[3]

    def _regen(self, dhp, now):
        if dhp in self.regens:
            return True
        self.rises = [r for r in self.rises if now - r[0] <= 3 * REGEN_EVERY + 1]
        for r in self.rises:
            k = round((now - r[0]) / REGEN_EVERY)
            if r[1] == dhp and k >= 1 and abs(now - r[0] - k * REGEN_EVERY) <= REGEN_SLACK:
                self.regens.add(dhp)
                if r[2]:
                    self.alone["hp"] = max(0, self.alone["hp"] - 1)
                    self._sync()
                self.rises.remove(r)
                return True
        return False

    def _usable(self, p):
        return all(not p.get(k) or not self.pet(k) or p["name"] == self.pet(k) or p["name"] in self.bar
                   for k in ("hp", "mp"))

    def _fits(self, delta, total, capped, loose=False):
        if loose:
            return self.up < delta <= total + self.up, 0
        if total == 0:
            return delta <= self.up, 0
        if capped:
            return total >= delta - self.up, max(0, delta - total)
        r = delta - total
        return -self.down <= r <= self.up, abs(r)

    def _explain(self, dhp, hp_cap, hpm, dmp, mp_cap, mpm, loose=False):
        best, best_key = None, None
        pots = [p for p in self.potions if self._usable(p)]
        order = {p["name"]: i for i, p in enumerate(pots)}
        pet = {k: self.pet(k) for k in ("hp", "mp")}
        for n in range(1, MAX_AT_ONCE + 1):
            for combo in combinations_with_replacement(pots, n):
                names = [p["name"] for p in combo]
                lh, lm = (loose and pet[k] in names for k in ("hp", "mp"))
                if loose and not (lh or lm):
                    continue
                shp = sum(amount(p.get("hp"), hpm) for p in combo)
                smp = sum(amount(p.get("mp"), mpm) for p in combo)
                ok_h, r_h = self._fits(dhp, shp, hp_cap, lh)
                ok_m, r_m = self._fits(dmp, smp, mp_cap, lm)
                if not (ok_h and ok_m):
                    continue
                pref = sum(0 if p["name"] in self.last.values() else 1 for p in combo)
                key = (n, round((r_h + r_m) / self.up), pref, sum(order[p["name"]] for p in combo))
                if best_key is None or key < best_key:
                    best, best_key = combo, key
            if best:
                return best
        return None

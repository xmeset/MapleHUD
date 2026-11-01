WINDOW_GRACE = 6.0
MAX_STEP = 300_000


class MesoCounter:
    """Mesos picked up, from the inventory's mesos count: every confirmed rise is earned, except at a
    shop, storage or trade window (or just after one), and a drop is spending. Never reset by map
    changes; the inventory only has to be opened now and then. A number seen only once (inventory
    opened for a moment) is believed when the next number is at least as big. A rise that spans the
    start of a run (end of grind, pause, reset) only counts for the part of the time after it."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.base = None
        self.gained = 0
        self.pending, self.seen, self.pending_ok = None, 0, False
        self.window_until = 0.0
        self.looks = 0
        self.base_at = self.pending_at = self.cut_at = 0.0
        self.on = False

    def cut(self, now):
        self.cut_at = now

    def tick(self, on, now):
        if on and not self.on:
            self.cut(now)
        self.on = on

    def note_window(self, now):
        self.window_until = now + WINDOW_GRACE

    def _take(self, value, ok, at):
        self.looks += 1
        base, self.base = self.base, value
        base_at, self.base_at = self.base_at, at
        if base is None:
            return None
        delta = value - base
        if ok and 0 < delta <= MAX_STEP:
            if base_at < self.cut_at < at:
                delta = round(delta * (at - self.cut_at) / (at - base_at))
            if delta <= 0:
                return None
            self.gained += delta
            return delta
        return None

    def feed(self, value, window, counting, now):
        if window:
            self.note_window(now)
        ok = counting and now >= self.window_until
        if value == self.base:
            self.base_at = now
        if value == self.pending:
            self.seen += 1
            return self._take(value, ok, self.pending_at) if self.seen == 2 else None
        got = None
        p = self.pending
        if self.seen == 1 and p is not None and self.base is not None and self.base < p <= value:
            got = self._take(p, self.pending_ok, self.pending_at)
        self.pending, self.seen, self.pending_ok, self.pending_at = value, 1, ok, now
        return got

    def fresh(self):
        return self.base is not None and self.base_at >= self.cut_at

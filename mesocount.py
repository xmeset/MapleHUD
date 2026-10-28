WINDOW_GRACE = 6.0
MAX_STEP = 300_000


class MesoCounter:
    """Mesos picked up, from the inventory's mesos count: every confirmed rise is earned, except at a
    shop, storage or trade window (or just after one), and a drop is spending. Never reset by map
    changes; the inventory only has to be opened now and then."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.base = None
        self.gained = 0
        self.pending, self.seen = None, 0
        self.window_until = 0.0
        self.looks = 0

    def note_window(self, now):
        self.window_until = now + WINDOW_GRACE

    def feed(self, value, window, counting, now):
        if window:
            self.note_window(now)
        if value != self.pending:
            self.pending, self.seen = value, 1
            return None
        self.seen += 1
        if self.seen != 2:
            return None
        self.looks += 1
        base, self.base = self.base, value
        if base is None:
            return None
        delta = value - base
        if delta > 0 and counting and now >= self.window_until and delta <= MAX_STEP:
            self.gained += delta
            return delta
        return None

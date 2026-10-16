"""Row-matching stitcher for scrolling capture (exact port of ScrollStitcher in
windows/src/ScrollCapture.cs). Kept free of UI so it can be tested on synthetic frames.
scrollcapture.py drives it with real scrolling; the self-test with a synthetic page.

Frames are opaque cairo ImageSurfaces (FORMAT_ARGB32) of identical size.
"""

import bisect

import cairo

ADDED, NO_MOVEMENT, NO_MATCH = "Added", "NoMovement", "NoMatch"


class _Rows:
    __slots__ = ("hash", "uniform")

    def __init__(self, h):
        self.hash = [0] * h
        self.uniform = [False] * h


class _Segment:
    __slots__ = ("frame", "y", "height")

    def __init__(self, frame, y, height):
        self.frame = frame
        self.y = y
        self.height = height


class ScrollStitcher:
    MIN_OVERLAP = 12

    def __init__(self):
        self.segments = []
        self.frames = []
        self.prev_rows = None
        self.frame_h = 0
        self.total_height = 0
        self.last_shift = 0
        self.last_usable_height = 0

    @property
    def frame_count(self):
        return len(self.frames)

    @staticmethod
    def _analyze(surface):
        surface.flush()
        w, h, stride = surface.get_width(), surface.get_height(), surface.get_stride()
        data = surface.get_data()
        # Skip the right edge: a moving scrollbar thumb would make every row look different.
        x0 = min(4, w // 4)
        x1 = max(x0 + 1, w - min(28, w // 4))
        n = x1 - x0
        rows = _Rows(h)
        for y in range(h):
            o = y * stride
            row = bytes(data[o + x0 * 4: o + x1 * 4])
            # Python's bytes hash stands in for the FNV-1a hash of the C# version: only equality matters.
            rows.hash[y] = hash(row)
            rows.uniform[y] = row == row[:4] * n
        return rows

    def add_first(self, frame):
        self.frames.append(frame)
        self.frame_h = frame.get_height()
        self.prev_rows = self._analyze(frame)
        self.segments.append(_Segment(frame, 0, self.frame_h))
        self.total_height = self.frame_h

    def add(self, frame):
        cur = self._analyze(frame)
        prev = self.prev_rows
        h = self.frame_h
        top = bottom = 0
        while top < h and cur.hash[top] == prev.hash[top]:
            top += 1
        if top == h:
            return NO_MOVEMENT
        while bottom < h - top and cur.hash[h - 1 - bottom] == prev.hash[h - 1 - bottom]:
            bottom += 1
        # Unchanged bands at the edges are sticky headers/footers (or browser chrome).
        top = min(top, h * 2 // 5)
        bottom = min(bottom, h * 2 // 5)
        usable = h - top - bottom
        self.last_usable_height = usable

        # Rows that take part in the comparison (uniform rows say nothing about the shift).
        candidates = [i for i in range(top, h - bottom) if not cur.uniform[i]]
        best_d = -1
        best_score = 0.0
        for d in range(1, usable - self.MIN_OVERLAP + 1):
            # Same range as the C# loop: i from top while i + d < h - bottom.
            limit = bisect.bisect_left(candidates, h - bottom - d)
            total = limit
            if total < 6:
                continue
            matches = 0
            ph = prev.hash
            ch = cur.hash
            for k in range(limit):
                i = candidates[k]
                if ch[i] == ph[i + d]:
                    matches += 1
            score = matches / float(total)
            if score > best_score + 1e-9:
                best_score = score
                best_d = d
        if best_d < 0 or best_score < 0.9:
            return NO_MATCH

        # Drop the previous frame's footer, then append the newly revealed rows plus the current footer.
        self._trim(bottom)
        self.segments.append(_Segment(frame, h - bottom - best_d, best_d + bottom))
        self.total_height += best_d + bottom
        self.frames.append(frame)
        self.prev_rows = cur
        self.last_shift = best_d
        return ADDED

    def _trim(self, rows):
        self.total_height -= rows
        while rows > 0 and self.segments:
            last = self.segments[-1]
            take = min(rows, last.height)
            last.height -= take
            rows -= take
            if last.height == 0:
                self.segments.pop()

    def compose(self):
        w = self.frames[0].get_width()
        result = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, max(1, self.total_height))
        cr = cairo.Context(result)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        y = 0
        for s in self.segments:
            if s.height <= 0:
                continue
            cr.save()
            cr.rectangle(0, y, w, s.height)
            cr.clip()
            cr.set_source_surface(s.frame, 0, y - s.y)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
            cr.restore()
            y += s.height
        result.flush()
        return result

    def dispose_frames(self):
        self.frames = []
        self.segments = []

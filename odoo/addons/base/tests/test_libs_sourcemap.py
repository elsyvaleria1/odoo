from odoo.libs.fixed_window import FixedWindowLimiter
from odoo.libs.sourcemap import SourceMap, encode_vlq, iter_segments
from odoo.tests.common import BaseCase


def _mappings(lines):
    previous = [0, 0, 0, 0]
    out = []
    for segments in lines:
        column = 0
        encoded = []
        for segment in segments:
            fields = [segment[0] - column]
            column = segment[0]
            for slot, value in enumerate(segment[1:]):
                fields.append(value - previous[slot])
                previous[slot] = value
            encoded.append(encode_vlq(*fields))
        out.append(",".join(encoded))
    return ";".join(out)


class TestSourceMap(BaseCase):
    def test_a_value_survives_the_round_trip(self):
        for value in (0, 1, -1, 15, 16, -16, 31, 32, 1_234_567, -987_654):
            [segment] = iter_segments(encode_vlq(value, 0, 0, 0))
            self.assertEqual(segment.column, value)

    def test_segments_run_on_across_lines(self):
        mappings = _mappings([[(0, 0, 0, 0), (10, 1, 5, 2)], [(4, 1, 6, 0, 3)]])
        segments = list(iter_segments(mappings))
        self.assertEqual(
            [(s.line, s.column, s.source, s.source_line, s.name) for s in segments],
            [(0, 0, 0, 0, None), (0, 10, 1, 5, None), (1, 4, 1, 6, 3)],
        )
        self.assertEqual(len(list(iter_segments(mappings, until_line=0))), 2)

    def test_a_generated_position_finds_its_source_line(self):
        source_map = SourceMap(
            {
                "sources": ["a.js", "b.js"],
                "sourcesContent": ["first\nsecond", "x\ny\nthe line"],
                "names": ["fn"],
                "mappings": _mappings([[(0, 0, 1, 0), (20, 1, 2, 4, 0)]]),
            }
        )
        found = source_map.locate([(0, 5), (0, 20), (0, 99), (3, 0)])
        self.assertEqual(found[0, 5].source, "a.js")
        self.assertEqual(found[0, 5].text, "second")
        self.assertEqual(found[0, 20].text, "the line")
        self.assertEqual(found[0, 20].name, "fn")
        self.assertEqual(found[0, 99].source, "b.js", "the segment before it")
        self.assertIsNone(found[3, 0], "a line with no mapping")

    def test_a_map_without_sources_content_still_locates(self):
        source_map = SourceMap(
            {"sources": ["a.js"], "mappings": _mappings([[(0, 0, 7, 0)]])}
        )
        original = source_map.locate([(0, 3)])[0, 3]
        self.assertEqual(
            (original.source, original.line, original.text), ("a.js", 7, None)
        )


class TestFixedWindowLimiter(BaseCase):
    def test_a_key_is_limited_past_its_window_limit(self):
        limiter = FixedWindowLimiter(window=60, limit=3)
        self.assertEqual(
            [limiter.is_limited("k") for _ in range(5)],
            [False, False, False, True, True],
        )
        self.assertFalse(limiter.is_limited("other"))

    def test_the_key_map_stays_bounded(self):
        limiter = FixedWindowLimiter(window=60, limit=3, max_keys=100)
        for i in range(250):
            limiter.is_limited(f"k{i}")
        self.assertLessEqual(len(limiter._state), 101)

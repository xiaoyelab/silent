#!/usr/bin/env python3
"""test_gaps.py — gaps.py 的「每条检查都必须能红」测试。

红不了的检查是装饰品（2026-11-06 起的规矩）。所以每条检查配一个必须失败
的样本，红不出来就是测试自己的失败。
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gaps  # noqa: E402


def write(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def run(path, **kw):
    argv = [path]
    for k, v in kw.items():
        flag = f"--{k.replace('_', '-')}"
        argv.append(flag if v is True else f"{flag}={v}")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gaps.main(argv)
    return code, buf.getvalue()


class GapsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = []

    def tearDown(self):
        for p in self.tmp:
            try:
                os.unlink(p)
            except OSError:
                pass

    def mk(self, rows):
        p = write(rows)
        self.tmp.append(p)
        return p

    def test_healthy(self):
        now = time.time()
        rows = [{"ts": now - 9 * 600 + i * 600} for i in range(10)]
        code, out = run(self.mk(rows), interval=600, max_gap=600)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_gap_goes_red(self):
        now = time.time()
        rows = [{"ts": now - 3600 * 3}, {"ts": now - 3600 * 2}, {"ts": now}]
        code, out = run(self.mk(rows), max_gap=3600)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL    gaps", out)

    def test_order_goes_red(self):
        rows = [{"ts": 1000}, {"ts": 900}, {"ts": 1100}]
        code, out = run(self.mk(rows))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL    order", out)

    def test_duplicates_go_red_then_allowed(self):
        rows = [{"ts": 1000}, {"ts": 1000}, {"ts": 1600}]
        code, out = run(self.mk(rows))
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL    duplicates", out)
        code2, out2 = run(self.mk(rows), allow_dupes=True)
        self.assertIn("PASS    duplicates", out2)

    def test_bad_line_goes_red(self):
        p = self.mk([{"ts": 1000}, {"nope": 1}])
        code, out = run(p)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL    parse", out)

    def test_empty_is_unknown_not_pass(self):
        code, out = run(self.mk([]))
        self.assertEqual(code, 3, out)
        self.assertIn("UNKNOWN empty", out)

    def test_stale_tail_is_unknown_not_fail(self):
        old = time.time() - 10 * 3600
        rows = [{"ts": old - 600}, {"ts": old}]
        code, out = run(self.mk(rows), max_gap=600)
        self.assertEqual(code, 3, out)
        self.assertIn("UNKNOWN freshness", out)

    def test_coverage_goes_red(self):
        # 10 个间隔里只写 4 条
        rows = [{"ts": i * 600} for i in (0, 3, 6, 9)]
        code, out = run(self.mk(rows), interval=600, max_gap=1800)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL    coverage", out)

    def test_unreadable_file_is_unknown(self):
        code, out = run("/nonexistent/nope/nope.jsonl")
        self.assertEqual(code, 3, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

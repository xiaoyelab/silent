#!/usr/bin/env python3
"""test_fixture_scan.py — 扫描器自己也要能被证明会红。

三条：① 有一个 checks + 能红的 fixture → 0；② 去掉 fixture → 1 且点出文件名；
③ 目录里一个 checks 都没有 → 3（看不见，不是干净）。
"""

import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fixture_scan  # noqa: E402

CHECKS = """from silent import check, UNKNOWN

@check("c1", "样例检查")
def _():
    return True, "ok"
"""

FIXTURE = """import sys
print("EXPECT_REDS 1")
print("RED c1: 坏样本")
sys.exit(0)
"""


class FixtureScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)
        os.environ["SILENT_DECL_LEDGER"] = str(self.d / ".ledger.jsonl")
        (self.d / "checks_x.py").write_text(CHECKS, encoding="utf-8")

    def tearDown(self):
        os.environ.pop("SILENT_DECL_LEDGER", None)
        self.tmp.cleanup()

    def test_green_with_fixture(self):
        (self.d / "test_checks_x.py").write_text(FIXTURE, encoding="utf-8")
        code, bad = fixture_scan.scan(self.d)
        self.assertEqual(code, 0, bad)

    def test_red_without_fixture(self):
        code, bad = fixture_scan.scan(self.d)
        self.assertEqual(code, 1)
        self.assertEqual(bad, ["checks_x.py"])

    def test_unknown_when_no_checks(self):
        (self.d / "checks_x.py").unlink()
        code, _bad = fixture_scan.scan(self.d)
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

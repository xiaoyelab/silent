#!/usr/bin/env python3
"""test_cases.py — 两个复现必须成立，而且构造修好之后必须**不再**成立。"""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c4 = load("c4", HERE / "case4_self_attesting" / "demo.py")
c13 = load("c13", HERE / "case1_3_status_drift" / "demo.py")
c5 = load("c5", HERE / "case5_never_matches" / "demo.py")


class Case4(unittest.TestCase):
    def test_reproduces(self):
        with tempfile.TemporaryDirectory() as d:
            c4.pack(d)
            ok_self, _ = c4.verify_self_attesting(d)
            ok_indep, _ = c4.verify_independent(d)
        self.assertTrue(ok_self)
        self.assertFalse(ok_indep)

    def test_negative_control_full_write(self):
        """写完整了，独立见证就该 PASS——复现必须只在截断时成立。"""
        with tempfile.TemporaryDirectory() as d:
            c4.pack(d, truncate_at=10)
            ok_self, _ = c4.verify_self_attesting(d)
            ok_indep, _ = c4.verify_independent(d)
        self.assertTrue(ok_self)
        self.assertTrue(ok_indep)


class Case5(unittest.TestCase):
    def test_reproduces(self):
        import datetime
        today = datetime.date(2026, 11, 21)
        due = {101: datetime.date(2026, 11, 18), 102: datetime.date(2026, 11, 25)}
        self.assertEqual(c5.buggy_count(c5.TOY), 0)
        self.assertEqual(c5.good_overdue(c5.TOY, due, today), [101])

    def test_good_matcher_sees_both(self):
        self.assertEqual(c5.good_count(c5.TOY, None), [101, 102])


class Case1to3(unittest.TestCase):
    def test_reproduces(self):
        self.assertEqual(c13.naive_open(c13.RECORDS),
                         ["9001", "9002", "9003"])
        drift = c13.status_drift(c13.RECORDS)
        self.assertEqual({rid for rid, _ in drift}, {"9001", "9002", "9003"})
        self.assertGreaterEqual(len(drift), 3)

    def test_negative_control_closed_properly(self):
        """把状态字段改对，漂移必须归零——检查器不是靠骂人成立。"""
        fixed = []
        for r in c13.RECORDS:
            r = dict(r)
            if any(w in c.lower() for c in r.get("comments", []) for w in c13.CLOSED_WORDS):
                r["status"] = "closed"
                r["closed_at"] = "2026-11-09T08:20Z"
                if r.get("accepting_submissions") is not None:
                    r["accepting_submissions"] = False
            if r.get("expiryTime"):
                r["status"] = "expired"
            fixed.append(r)
        self.assertEqual(c13.naive_open(fixed), [])
        self.assertEqual(c13.status_drift(fixed), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

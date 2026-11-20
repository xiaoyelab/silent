#!/usr/bin/env python3
"""fixture_scan.py — every `checks_*.py` must ship a `test_*.py` that can go red.

Why: a check that has never been observed failing is not evidence. In my own lab
the recurring failure was not "the canary broke" but "a new checker shipped without
a fixture", so the health check had never seen it go red.

    python3 fixture_scan.py [DIR]      # default: current directory

Exit: 0 every checks file has a fixture leg; 1 at least one is missing/broken;
3 no `checks_*.py` at all (that is "could not check", not "clean").

The leg itself is `silent.fixture_leg`: it runs `test_<stem>.py` next to the checks
file and expects it to print `EXPECT_REDS N` and `RED <name>` lines (see README).
"""

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import silent  # noqa: E402


def scan(directory):
    """返回 (exit_code, bad_names)。0 全有；1 有缺；3 一个 checks 文件都没有。"""
    d = pathlib.Path(directory)
    files = sorted(d.glob("checks_*.py"))
    if not files:
        print(f"no checks_*.py under {d} — could not check", file=sys.stderr)
        return 3, []
    bad = []
    for f in files:
        ok, msg, _meta = silent.fixture_leg(str(f))
        print(f"{'ok  ' if ok else 'MISS'} {f.name}: {msg}")
        if not ok:
            bad.append(f.name)
    return (1 if bad else 0), bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=".")
    a = ap.parse_args(argv)
    code, bad = scan(a.dir)
    if code == 1:
        print(f"\n{len(bad)} 个 checks 文件没有能变红的 fixture：{', '.join(bad)}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

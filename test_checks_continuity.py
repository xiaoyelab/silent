#!/usr/bin/env python3
"""test_checks_continuity.py — 证明 checks_continuity 的三条检查都能红。

silent.py 的 fixture leg 会跑这个文件，并把 `RED <名字> ...` 行当成
「这一轮观察到红的证据」。EXPECT_REDS 必须等于实际打出的 RED 行数。
"""

import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import checks_continuity as cc  # noqa: E402

REDS = []


def _write(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _state_of(out):
    """check 函数返回 (bool, detail) 或 (state, detail)；统一成 (state, detail)。"""
    head, detail = out
    if isinstance(head, bool):
        return ("PASS" if head else "FAIL"), detail
    return str(head).upper(), detail


def _run(rows, **env):
    path = _write(rows)
    for k in list(os.environ):
        if k.startswith("CONTINUITY_"):
            del os.environ[k]
    os.environ["CONTINUITY_FILE"] = path
    os.environ.update({k: str(v) for k, v in env.items()})
    cc._CACHE.clear()
    try:
        return {name: fn() for name, fn in (("readable", cc._readable),
                                            ("contiguous", cc._contiguous),
                                            ("fresh", cc._fresh))}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def red(name, state, reason):
    REDS.append(name)
    print(f"RED {name} {state}: {reason}")


def main():
    now = time.time()

    # 1) 读不出来的行 → readable 必须红
    out = _run([{"ts": now - 120}, {"nope": 1}])
    state, detail = _state_of(out["readable"])
    assert state != "PASS", detail
    red("readable", state, detail)

    # 2) 空档超限 → contiguous 必须红
    out = _run([{"ts": now - 7200}, {"ts": now - 3600}, {"ts": now}], CONTINUITY_MAX_GAP=600)
    state, detail = _state_of(out["contiguous"])
    assert state == "FAIL", detail
    red("contiguous", state, detail)

    # 3) 末尾太旧 → fresh 必须是 UNKNOWN（看不见，不是干净）
    out = _run([{"ts": now - 10 * 3600}, {"ts": now - 9 * 3600}], CONTINUITY_MAX_GAP=3600)
    state, detail = _state_of(out["fresh"])
    assert state == "UNKNOWN", detail
    red("fresh", state, detail)

    print(f"EXPECT_REDS {len(REDS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

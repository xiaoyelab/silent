#!/usr/bin/env python3
"""checks_continuity.py — 把 gaps.py 的「断没断」包成 silent.py 的三态检查。

给客户（或给我自己）用同一套退出码：
    CONTINUITY_FILE=events.jsonl \\
    CONTINUITY_TS=t CONTINUITY_MAX_GAP=86400 \\
    python3 silent.py run checks_continuity.py

环境变量：
    CONTINUITY_FILE      必填，JSONL 路径
    CONTINUITY_TS        时间字段名，默认 ts
    CONTINUITY_MAX_GAP   允许的最大空档秒数，默认 3600
    CONTINUITY_INTERVAL  期望固定间隔；给了才查条数覆盖，默认 0（不查）
    CONTINUITY_ALLOW_DUPES=1  同一时间重复不算失败（流水类日志常这样）

三条检查：readable（读得出来）/ contiguous（顺序+空档+覆盖）/ fresh（末尾新不新）。
读不出来、文件空、末尾太旧，一律 UNKNOWN——看不见不冒充干净。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gaps  # noqa: E402
from silent import check, UNKNOWN as S_UNKNOWN  # noqa: E402

# gaps.py 用大写状态名（PASS/FAIL/UNKNOWN）；silent.py 用小写。这里统一按 gaps 的常量比。

_CACHE = {}


def _load():
    """跑一次，按检查名存结果；`_pre` 表示「连数据都没读到」。"""
    if "states" in _CACHE:
        return _CACHE["states"]

    path = os.environ.get("CONTINUITY_FILE", "").strip()
    if not path:
        _CACHE["states"] = {"_pre": (gaps.UNKNOWN, "no-file", "没给 CONTINUITY_FILE")}
        return _CACHE["states"]

    ts = os.environ.get("CONTINUITY_TS", "ts")
    try:
        rows, bad = gaps.load(path, ts)
    except OSError as e:
        _CACHE["states"] = {"_pre": (gaps.UNKNOWN, "read", f"读不到 {path}: {e}")}
        return _CACHE["states"]

    class _Args:
        max_gap = float(os.environ.get("CONTINUITY_MAX_GAP", "3600"))
        interval = float(os.environ.get("CONTINUITY_INTERVAL", "0"))
        allow_dupes = os.environ.get("CONTINUITY_ALLOW_DUPES", "") == "1"

    states = {name: (state, name, detail) for state, name, detail in gaps.check(rows, bad, _Args)}
    if not rows:
        states["_pre"] = (gaps.UNKNOWN, "empty", "文件里没有可读的行")
    _CACHE["states"] = states
    return states


def _pick(name):
    states = _load()
    if "_pre" in states:
        return states["_pre"]
    return states.get(name)


@check("readable", "每一行都要能读出时间；读不出就说看不见")
def _readable():
    r = _pick("parse")
    if r is None:
        return S_UNKNOWN, "文件里没有可读的行"
    if r[0] == gaps.UNKNOWN:
        return S_UNKNOWN, r[2]
    return (r[0] == gaps.PASS), r[2]


@check("contiguous", "时间不倒回、没有超出允许的空档、条数够")
def _contiguous():
    r = _pick("gaps")
    if r is None:
        return S_UNKNOWN, "没有可判断的空档"
    if r[0] == gaps.UNKNOWN:
        return S_UNKNOWN, r[2]
    bad = []
    for name in ("order", "gaps", "coverage"):
        res = _pick(name)
        if res is not None and res[0] == gaps.FAIL:
            bad.append(res[2])
    if bad:
        return False, "; ".join(bad)
    return True, r[2]


@check("fresh", "最后一条要够新；末尾太旧就是看不见，不是干净")
def _fresh():
    r = _pick("freshness")
    if r is None:
        return S_UNKNOWN, "没有可判断的末尾"
    if r[0] == gaps.UNKNOWN:
        return S_UNKNOWN, r[2]
    return (r[0] == gaps.PASS), r[2]

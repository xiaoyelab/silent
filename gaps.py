#!/usr/bin/env python3
"""gaps.py — 「这份记录断没断？」

为什么有（2026-11-14 夜里）：徐家汇观象台 1872–1945 每年 7 月 7 日都有一张观测表，
抗战里没人发工资也照记；它 1947 年被「纸上关闭」，记录却没断。
连续记录的价值不在「有记录」，在「断没断」能被查出来。

泛化成一句话：给一份带时间戳的记录（JSONL），回答四个问题——
    · 有没有读不出来的行？（看不清就说看不清，不当通过）
    · 时间是不是一路向前？有没有倒回？
    · 有没有重复的同一条？
    · 有没有超过允许间隔的空档、该有的条数够不够？

退出码跟 silent.py 一致：
    0  全部通过
    1  至少一条失败（真断了）
    3  没有失败，但至少一条**看不见**（文件空 / 末尾太旧，判断不了）

用法：
    python3 gaps.py data.jsonl
    python3 gaps.py data.jsonl --ts ts --max-gap 3600 --interval 300
    python3 gaps.py data.jsonl --json

注意：如果这份记录本来就可能同一分钟写两行（比如多条流水共用一个时间字段），
用 --allow-dupes，否则重复检查会报合法的重复——假警报会教人忽略检查。
"""

import argparse
import datetime
import json
import re
import sys
import time

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def parse_ts(v):
    """epoch 秒 / 毫秒 / ISO8601（带时区，或裸的时间按本机时区）。"""
    if isinstance(v, bool):
        raise ValueError("bool 不是时间")
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e12 else x
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return parse_ts(float(s))
    s2 = s.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
    return dt.timestamp()


def load(path, field):
    rows, bad = [], []
    with open(path, "rb") as f:
        for i, raw in enumerate(f, 1):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rows.append((i, parse_ts(obj[field])))
            except Exception as e:  # noqa: BLE001
                bad.append((i, f"{type(e).__name__}: {e}"))
    return rows, bad


def check(rows, bad, args, now=None):
    now = time.time() if now is None else now
    out = []

    if not rows and not bad:
        return [(UNKNOWN, "empty", "文件里没有可读的行")]

    if bad:
        head = "; ".join(f"行 {i}: {m}" for i, m in bad[:3])
        out.append((FAIL, "parse", f"{len(bad)} 行读不出时间（{head}）"))
    else:
        out.append((PASS, "parse", f"{len(rows)} 行都有时间"))

    if rows:
        ts = [t for _, t in rows]

        decreases = [(rows[i][0], rows[i - 1][0]) for i in range(1, len(ts)) if ts[i] < ts[i - 1]]
        if decreases:
            line_now, line_prev = decreases[0]
            out.append((FAIL, "order", f"{len(decreases)} 处时间倒回，第一处在第 {line_now} 行（前一行 {line_prev}）"))
        else:
            out.append((PASS, "order", "时间非递减"))

        seen, dupes = set(), []
        for line_no, t in rows:
            key = round(t, 6)
            if key in seen:
                dupes.append(line_no)
            seen.add(key)
        if dupes and not args.allow_dupes:
            out.append((FAIL, "duplicates", f"{len(dupes)} 行与前面某行同一时间，第一处第 {dupes[0]} 行"))
        elif dupes:
            out.append((PASS, "duplicates", f"{len(dupes)} 行同时间（--allow-dupes 已放行）"))
        else:
            out.append((PASS, "duplicates", "没有重复时间"))

        gaps = [(ts[i] - ts[i - 1], rows[i][0], rows[i - 1][0]) for i in range(1, len(ts))]
        worst = max(gaps, default=(0, 0, 0))
        over = [g for g in gaps if g[0] > args.max_gap]
        if over:
            out.append((FAIL, "gaps", f"{len(over)} 处超过 {args.max_gap:g}s；最大 {worst[0]:.0f}s（第 {worst[1]} 行 vs {worst[2]} 行）"))
        else:
            out.append((PASS, "gaps", f"最大空档 {worst[0]:.0f}s ≤ {args.max_gap:g}s"))

        if args.interval and len(ts) >= 2:
            span = ts[-1] - ts[0]
            expected = int(span // args.interval) + 1
            missing = expected - len(ts)
            tol = max(1, int(expected * 0.02))
            if missing > tol:
                out.append((FAIL, "coverage", f"按 {args.interval:g}s 一条应有约 {expected} 条，实际 {len(ts)} 条，少 {missing} 条"))
            else:
                out.append((PASS, "coverage", f"应有约 {expected} 条，实际 {len(ts)} 条"))

        age = now - ts[-1]
        limit = args.max_gap * 2
        if age > limit:
            out.append((UNKNOWN, "freshness", f"最后一条在 {age:.0f}s 前（> {limit:g}s），现在断没断判断不了"))
        else:
            out.append((PASS, "freshness", f"最后一条在 {age:.0f}s 前"))

    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="检查一份 JSONL 记录断没断")
    ap.add_argument("file")
    ap.add_argument("--ts", default="ts", help="时间字段名（默认 ts）")
    ap.add_argument("--max-gap", type=float, default=3600.0, help="允许的最大间隔秒数（默认 3600）")
    ap.add_argument("--interval", type=float, default=0.0, help="期望的固定间隔秒数；给了才查条数覆盖（默认不查）")
    ap.add_argument("--allow-dupes", action="store_true", help="同一时间重复不算失败")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        rows, bad = load(args.file, args.ts)
    except OSError as e:
        print(f"{UNKNOWN}  file  {e}")
        return 3
    out = check(rows, bad, args)

    if args.json:
        print(json.dumps({
            "file": args.file,
            "exit": 1 if any(s == FAIL for s, _, _ in out) else 3 if any(s == UNKNOWN for s, _, _ in out) else 0,
            "checks": [{"state": s, "name": n, "detail": d} for s, n, d in out],
        }, ensure_ascii=False))
    else:
        for s, n, d in out:
            print(f"{s:7} {n:10} {d}")

    if any(s == FAIL for s, _, _ in out):
        return 1
    if any(s == UNKNOWN for s, _, _ in out):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

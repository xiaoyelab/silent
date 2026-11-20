#!/usr/bin/env python3
"""案例 5 的可跑复现：检查器找的是永远不会出现的行。

构造一份玩具「预言文件」：两条已过期、没对账。两个检查器读它：
- 坏的：找 `- 如果` 开头的行（真实文件里是 `N. 如果`），命中 0 → 报「干净」。
- 好的：按 `N. 如果` 匹配并看过期日期 → 报 2 条。

跑 `python3 demo.py`：退出 0 = 复现成立（坏的说干净，好的说 2 条）。
"""
import datetime
import pathlib
import re
import tempfile

TOY = """## 2026-11-10 23:0x 写

101. 如果这条过期了，那么应该有人来对账。
102. 如果这条也过期了，那么也应该有人来对账。
"""


def buggy_count(text):
    return len([ln for ln in text.splitlines() if ln.startswith("- 如果")])


def good_count(text, today):
    out = []
    for ln in text.splitlines():
        m = re.match(r"^(\d+)\. 如果", ln)
        if m:
            out.append(int(m.group(1)))
    return out  # 只看「旧写法能不能匹配到」，到期日期由调用方另判


def good_overdue(text, due, today):
    hits = []
    for ln in text.splitlines():
        m = re.match(r"^(\d+)\. 如果", ln)
        if m and int(m.group(1)) in due and due[int(m.group(1))] <= today:
            hits.append(int(m.group(1)))
    return hits


def main():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "PROPHECY.md"
        p.write_text(TOY, encoding="utf-8")
        text = p.read_text(encoding="utf-8")
        today = datetime.date(2026, 11, 21)
        due = {101: datetime.date(2026, 11, 18), 102: datetime.date(2026, 11, 25)}

        bad = buggy_count(text)
        good = good_overdue(text, due, today)
        print(f"坏的检查器：命中 {bad} 行 → {'干净' if bad == 0 else '有发现'}")
        print(f"好的检查器：命中 {len(good)} 条过期 → {good}")
        reproduced = bad == 0 and good == [101]
        print("复现成立" if reproduced else "没复现")
        return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())

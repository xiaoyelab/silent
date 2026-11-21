"""test_order_independence.py — 报告按名字接，不按位置接。

为什么有（2026-11-22 07:0x）：Colony 上的 bothireagent 说，那条「按名字映射」的规则
不需要事故来撑——一个「把 fixture 顺序换掉、报告仍然对得上」的测试，比任何轶事都有分量。
这个文件就是那个测试（以及在它下面那个反例）。

做法：
1. 同一组检查（同名、同状态），用两种注册顺序各跑一次跑器；
2. 两次的 name→state 映射必须完全一样；
3. 反例：把两次的名单按下标硬接，一定错位——证明「按位置接」这条错法能被这个测试抓到。
"""
import json
import subprocess
import sys
import tempfile
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

HEADER = '''\
"""临时检查文件（由 test_order_independence.py 生成）。"""
from silent import check
'''

# 每个名字的行为固定，与注册顺序无关（这才是「按名字映射」能成立的前提）。
BODIES = {
    "alpha": '    return True, "ok"',
    "mike": '    raise RuntimeError("看不见的那条")',
    "zeta": '    return False, "红的那条"',
}

EXPECT = {"alpha": "pass", "mike": "unknown", "zeta": "fail"}
ORDERS = [("zeta", "alpha", "mike"), ("mike", "zeta", "alpha")]


def make(tmp, order):
    path = os.path.join(tmp, "order_%s.py" % "_".join(order))
    parts = [HEADER, ""]
    for name in order:
        parts.append("@check(%r)" % name)
        parts.append("def check_%s():" % name)
        parts.append('    """名字固定行为，与注册顺序无关。"""')
        parts.append(BODIES[name])
        parts.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return path


def run(path):
    p = subprocess.run([PY, os.path.join(HERE, "silent.py"), "run", path, "--json"],
                       capture_output=True, text=True, timeout=120)
    d = json.loads(p.stdout)
    return d, [r["name"] for r in d["results"]], {r["name"]: r["state"] for r in d["results"]}


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        runs = []
        for order in ORDERS:
            d, names, mapping = run(make(tmp, order))
            runs.append((order, names, mapping))
            ok = mapping == EXPECT
            print(f"{'ok  ' if ok else 'BAD '} 顺序 {order}: name→state = {mapping}（期望 {EXPECT}）")
            if not ok:
                failures.append(("mapping", order))
            ok = names == list(order)
            print(f"{'ok  ' if ok else 'BAD '}   跑器按注册顺序输出：{names}")
            if not ok:
                failures.append(("order", order))

        (o1, n1, m1), (o2, n2, m2) = runs
        ok = m1 == m2 == EXPECT
        print(f"{'ok  ' if ok else 'BAD '} 两种注册顺序下 name→state 完全一致")
        if not ok:
            failures.append(("independent", o1, o2))

        # 反例：按下标硬接，一定错位。这是「按位置接」那条错法的现场。
        by_index = {n1[i]: m2[n2[i]] for i in range(len(n1))}
        ok = by_index != EXPECT
        sample = [f"{k}: {by_index.get(k)}" for k in sorted(EXPECT) if by_index.get(k) != EXPECT[k]]
        print(f"{'ok  ' if ok else 'BAD '} 反例：按下标硬接会错（{', '.join(sample)}）")
        if not ok:
            failures.append(("negative-control", by_index))

    print()
    if failures:
        print(f"FAIL：{len(failures)} 条")
        for f in failures:
            print(" ", f)
        return 1
    print("PASS：报告按名字接，换顺序不会错位")
    return 0


if __name__ == "__main__":
    sys.exit(main())

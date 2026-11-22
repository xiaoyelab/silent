"""test_order_independence.py — 报告按名字接，不按位置接。

为什么有（2026-11-22 07:0x）：Colony 上的 bothireagent 说，那条「按名字映射」的规则
不需要事故来撑——一个「把 fixture 顺序换掉、报告仍然对得上」的测试，比任何轶事都有分量。
07:0x 第一版只跑两种固定顺序；10:0x 他又补了一条：**两种固定顺序只能抓到已知的那种错位**，
再加几组带种子的打乱，才能抓到「检查排到第五位时才出现」的错位（失败时把种子打出来）。

这个文件现在做三件事：
1. 五个同名检查（状态各不相同），用两种固定顺序各跑一次跑器，name→state 必须一致；
2. 用固定种子的随机顺序再跑几组，同样必须一致；失败时打印种子以便复现；
3. 反例：把某两次的名单按下标硬接，一定错位——证明「按位置接」这条错法能被这个测试抓到。
"""
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

HEADER = '''\
"""临时检查文件（由 test_order_independence.py 生成）。"""
from silent import check
'''

# 每个名字的行为固定，与注册顺序无关（这才是「按名字映射」能成立的前提）。
BODIES = {
    "alpha": '    return True, "ok"',
    "bravo": '    return False, "红的那条"',
    "charlie": '    raise RuntimeError("看不见的那条")',
    "delta": '    return True, "ok"',
    "echo": '    return False, "红的那条"',
}
EXPECT = {"alpha": "pass", "bravo": "fail", "charlie": "unknown",
          "delta": "pass", "echo": "fail"}
NAMES = list(EXPECT)
FIXED_ORDERS = [NAMES, list(reversed(NAMES))]
SHUFFLE_SEEDS = [0, 7, 42]


def make(tmp, order, tag):
    path = os.path.join(tmp, "order_%s.py" % tag)
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
    return [r["name"] for r in d["results"]], {r["name"]: r["state"] for r in d["results"]}


def check_one(desc, order, tmp, tag, failures):
    names, mapping = run(make(tmp, order, tag))
    ok = mapping == EXPECT
    print(f"{'ok  ' if ok else 'BAD '} {desc}: name→state 与名字一致" + ("" if ok else f"（实得 {mapping}）"))
    if not ok:
        failures.append((desc, mapping))
    ok = names == list(order)
    print(f"{'ok  ' if ok else 'BAD '}   跑器按注册顺序输出：{names}")
    if not ok:
        failures.append((desc + " 顺序", names))
    return names, mapping


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        runs = []
        for i, order in enumerate(FIXED_ORDERS):
            runs.append(check_one(f"固定顺序 {i+1}", order, tmp, f"fixed{i}", failures))

        for seed in SHUFFLE_SEEDS:
            order = NAMES[:]
            random.Random(seed).shuffle(order)
            try:
                check_one(f"打乱 seed={seed}", order, tmp, f"seed{seed}", failures)
            except Exception as e:  # noqa: BLE001
                failures.append((f"打乱 seed={seed}", repr(e)))
                print(f"BAD  打乱 seed={seed}: {e!r}（种子打出来才能复现）")

        (n1, m1), (n2, m2) = runs[0], runs[1]
        ok = m1 == m2 == EXPECT
        print(f"{'ok  ' if ok else 'BAD '} 两种固定顺序下 name→state 完全一致")
        if not ok:
            failures.append(("independent", m1, m2))

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
    print("PASS：报告按名字接；固定顺序与 %d 组打乱都不会错位" % len(SHUFFLE_SEEDS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

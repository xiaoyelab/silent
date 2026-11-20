"""test_silent.py — 跑器的退出码契约（0 通过 / 1 失败 / 3 看不见 / 2 跑器坏了）。

    python3 test_silent.py
"""

import json
import subprocess
import sys

PY = sys.executable
HERE = __file__.rsplit("/", 1)[0]

CASES = [
    # (说明, argv 追加, 期望退出码)
    ("只有通过的一条", ["--only", "ok"], 0),
    ("有失败的一条", ["--only", "nope"], 1),
    ("检查抛异常 = 看不见", ["--only", "boom"], 3),
    ("看不见 + --strict = 失败", ["--only", "boom", "--strict"], 1),
    ("超时 = 看不见", ["--only", "slow", "--timeout", "0.3"], 3),
    ("混在一起：有失败就 1（不是 3）", [], 1),
    ("--only 没匹配到 = 跑器用法错", ["--only", "没有这个"], 2),
]

failures = []
for desc, extra, want in CASES:
    p = subprocess.run([PY, f"{HERE}/silent.py", "run", f"{HERE}/demo_checks.py", *extra],
                       capture_output=True, text=True, timeout=120)
    ok = p.returncode == want
    print(f"{'ok  ' if ok else 'BAD '} {desc}: exit {p.returncode}（期望 {want}）")
    if not ok:
        failures.append((desc, p.returncode, want, p.stdout[-300:], p.stderr[-300:]))

# JSON 里必须三条状态都在，且 unknown 有条目
p = subprocess.run([PY, f"{HERE}/silent.py", "run", f"{HERE}/demo_checks.py", "--json", "--timeout", "0.3"],
                   capture_output=True, text=True, timeout=120)
try:
    d = json.loads(p.stdout)
    states = {r["state"] for r in d["results"]}
    # 2026-11-09：fixture 结论必须并进同一个 JSON；并排一行 print 就破坏了 --json 契约。
    ok = ({"pass", "fail", "unknown"} <= states and d["counts"]["unknown"] >= 1
          and isinstance(d.get("fixture_leg"), dict))
    print(f"{'ok  ' if ok else 'BAD '} --json 三态都出现且含 fixture_leg：{sorted(states)} {d['counts']}")
    if not ok:
        failures.append(("json", 0, 0, p.stdout[:300], p.stderr[:300]))
except json.JSONDecodeError as e:
    print(f"BAD  --json 不是 JSON：{e}")
    failures.append(("json-parse", 0, 0, p.stdout[:300], e))

# 检查文件不存在 = 跑器用法错，不能崩栈
p = subprocess.run([PY, f"{HERE}/silent.py", "run", "/nope/none.py"], capture_output=True, text=True, timeout=60)
ok = p.returncode == 2 and "Traceback" not in p.stderr
print(f"{'ok  ' if ok else 'BAD '} 检查文件不存在：exit {p.returncode}，stderr 有没有崩栈={'Traceback' in p.stderr}")
if not ok:
    failures.append(("missing-file", p.returncode, 2, p.stdout[:300], p.stderr[:300]))

print()
if failures:
    print(f"FAIL：{len(failures)} 条不符合契约")
    for f in failures:
        print(" ", f[0], f[1], "!=", f[2])
    sys.exit(1)
print("PASS：退出码契约全部符合")

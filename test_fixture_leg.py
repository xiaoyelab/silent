"""test_fixture_leg.py — sidecar 被删掉之后，声明历史不能假装「首次运行」。

2026-11-09 bothireagent 指出的洞：`.decl.json` 就躺在被描述的文件旁边，
删掉它，下一轮看起来就是第一次跑，没有旧声明可对照。
对策是另记一份 append-only 账本；这个文件验证账本真的起作用。

    python3 test_fixture_leg.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import silent  # noqa: E402

FIXTURE = """import sys
print("EXPECT_REDS N")
for i in range(N):
    print(f"RED check-{i}: 坏样本")
sys.exit(0)
"""

failures = []


def run(d, note_expected=None, label=""):
    ok, msg, meta = silent.fixture_leg(os.path.join(d, "check_foo.py"))
    hit = (note_expected is None and "**" not in msg) or (note_expected and note_expected in msg)
    print(f"{'ok  ' if hit else 'BAD '} {label}: {'OK' if ok else 'MISS'} {msg}")
    if not hit:
        failures.append(label)
    return meta


def write_fixture(d, n, with_decl=True):
    body = FIXTURE.replace("N", str(n))
    if not with_decl:
        body = "\n".join(l for l in body.splitlines() if "EXPECT_REDS" not in l)
    with open(os.path.join(d, "test_check_foo.py"), "w", encoding="utf-8") as f:
        f.write(body)


with tempfile.TemporaryDirectory() as d:
    ledger = os.path.join(d, ".ledger.jsonl")
    os.environ["SILENT_DECL_LEDGER"] = ledger
    open(os.path.join(d, "check_foo.py"), "w").write("# 被检查的文件\n")

    write_fixture(d, 4)
    meta = run(d, None, "首次跑，没有旧记录")
    hit = meta.get("declared") == 4 and meta.get("observed") == 4
    print(f"{'ok  ' if hit else 'BAD '} 机器可读计数：declared={meta.get('declared')} observed={meta.get('observed')}")
    if not hit:
        failures.append("meta 计数")
    run(d, None, "第二次跑，声明没变")

    sidecar = os.path.join(d, ".test_check_foo.py.decl.json")
    assert os.path.exists(sidecar), "sidecar 应该存在"
    os.remove(sidecar)
    run(d, "声明记录缺失", "删了 sidecar、读数没变")

    os.remove(sidecar)          # 上一轮已经把 sidecar 写回来了，要再删一次才是「同时还降了声明」
    write_fixture(d, 2)
    run(d, "按变化报", "删了 sidecar、声明从 4 降到 2")

    write_fixture(d, 2, with_decl=False)
    run(d, "声明不见了", "EXPECT_REDS 行被删掉")

if failures:
    print(f"\n{len(failures)} 个没中：{failures}")
    sys.exit(1)
print("\n全过：sidecar 删掉后，降声明和去声明都不再安静")

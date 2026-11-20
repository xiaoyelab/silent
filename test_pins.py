"""test_pins.py — 钉住清单（pins.py）的契约。

2026-11-17 建。它要证明四件在旧机制里看不见的事：
1. 只钉条数不够：把红 case A 换成 B、条数不变，现在会 MISS（缺 pinned 名字）。
2. 多出来的红不算失败，但必须写出来（新红未钉住）。
3. 没有钉住清单是「弱」，不是「红」——先说清楚，不假装。
4. 清单被改了要看得到（pins sha 记进 append-only 账本，下一轮对照）。
还有一条：--json 的 fixture_leg 里要有机器可读的 pins 字段（不是拼出来的字符串）。

    python3 test_pins.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pins      # noqa: E402
import silent    # noqa: E402

failures = []


def ok(label, cond, extra=""):
    print(("ok   " if cond else "BAD  ") + label + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        failures.append(label)


def write(path, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


CHECK = """from silent import check

@check("t", "契约用的检查")
def _():
    return True, "ok"
"""


def fixture(names, declared=None):
    body = "import sys\n"
    for n in names:
        body += f'print("RED {n}: 坏样本")\n'
    body += f'print("EXPECT_REDS {declared if declared is not None else len(names)}")\n'
    body += "sys.exit(0)\n"
    return body


with tempfile.TemporaryDirectory() as d:
    pins_path = os.path.join(d, "pins.json")
    ledger = os.path.join(d, ".ledger.jsonl")
    os.environ["SILENT_PINS"] = pins_path
    os.environ["SILENT_DECL_LEDGER"] = ledger
    checkfile = os.path.join(d, "check_foo.py")
    write(checkfile, CHECK)
    write(os.path.join(d, "test_check_foo.py"), fixture(["alpha", "beta"]))

    # 0) 两种 RED 行的格式都要能取名字（continuity 带 state；site/duami 不带）
    names = pins.names_from_stdout("RED readable FAIL: 读不出时间\nRED feed 比文章少要红: items 1/2\n")
    ok("两种 RED 行格式都取到名字", names == ["readable", "feed 比文章少要红"], repr(names))

    # 1) 没有清单：弱，但不是红
    leg_ok, msg, meta = silent.fixture_leg(checkfile)
    ok("没有钉住清单 → leg OK（弱，不是红）", leg_ok is True and meta.get("pins_ok") is None, msg)
    ok("没有清单时消息里说清楚", "没有钉住清单" in msg, msg)

    # 2) 钉住后：全部观察到
    good, msg, _ = pins.pin(checkfile, "2026-11-17 15:10")
    ok("pin 写作成功", good and os.path.exists(pins_path), msg)
    leg_ok, msg, meta = silent.fixture_leg(checkfile)
    ok("钉住的名字都在 → leg OK 且 pins_ok=True",
       leg_ok is True and meta.get("pins_ok") is True and meta.get("pinned") == 2, msg)

    # 3) 偷换 case（条数不变）必须红
    write(os.path.join(d, "test_check_foo.py"), fixture(["alpha", "beta2"]))
    leg_ok, msg, meta = silent.fixture_leg(checkfile)
    ok("换掉一条红、条数不变 → leg MISS", leg_ok is False, msg)
    ok("MISS 消息点名缺的那条", "beta" in msg and meta.get("pins_missing") == ["beta"], msg)

    # 4) 多出来的红：不算失败，但要写出来
    write(os.path.join(d, "test_check_foo.py"), fixture(["alpha", "beta", "gamma"]))
    leg_ok, msg, meta = silent.fixture_leg(checkfile)
    ok("新红未钉住 → leg 仍 OK", leg_ok is True and meta.get("pins_ok") is True, msg)
    ok("新红写进消息和 meta", "新红未钉住" in msg and meta.get("pins_extra") == ["gamma"], msg)

    # 5) 清单自身被改：下一轮要看得见（靠账本里的 pins_sha 对照）
    data, _ = pins.load()
    entry = data["test_check_foo.py"]
    entry["pinned"] = ["alpha", "beta", "gamma"]
    pins.save(data)
    _ok2, msg, _meta = silent.fixture_leg(checkfile)
    ok("清单被改 → 消息里有「钉住清单变了」", "钉住清单变了" in msg, msg)

    # 6) --json 里的 fixture_leg 是机器可读的，不是拼字符串
    env = dict(os.environ, SILENT_PINS=pins_path, SILENT_DECL_LEDGER=ledger)
    p = subprocess.run([sys.executable, os.path.join(HERE, "silent.py"), "run", checkfile, "--json"],
                       cwd=d, capture_output=True, text=True, env=env, timeout=120)
    payload = json.loads(p.stdout)
    fl = payload.get("fixture_leg", {})
    need = {"pins_ok", "pins_sha", "pinned", "pins_missing", "pins_extra"}
    ok("--json 带机器可读 pins 字段", p.returncode == 0 and need <= set(fl), str(sorted(fl)))

if failures:
    print(f"\n{len(failures)} 个没中：{failures}")
    sys.exit(1)
print("\n全过：钉住的是名字，不是条数；清单被改会留痕")

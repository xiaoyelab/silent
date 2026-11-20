#!/usr/bin/env python3
"""silent.py — 三态检查跑器。

为什么不是「通过/失败」两态：一个检查在**看不见**的时候必须能说出「看不见」。
两态的检查遇到读不到的输入，只能二选一——选「通过」就是静默失败，
选「失败」就是假警报，而假警报会教人忽略这个检查。两种都让检查失去意义。

用法：

    # 写一个检查文件，里面用 @check 装饰器登记
    # checks_acme.py
    from silent import check, UNKNOWN

    @check("empty-vs-blind", "空列表必须回显它应用的筛选条件")
    def _(): 
        r = get("/v1/search?q=zzzz")
        if r.status == 503:
            return UNKNOWN, "上游 503，这次判断不了"
        return bool(r.json.get("filters_applied")), f"filters_applied={r.json.get('filters_applied')}"

    # 跑
    python3 silent.py run checks_acme.py
    python3 silent.py run checks_acme.py --json
    python3 silent.py run checks_acme.py --strict     # UNKNOWN 也算失败（CI 用）
    python3 silent.py pin checks_acme.py              # 把这一轮的红名字钉住（清单在 pins.json）

退出码：
    0  全部通过
    1  至少一条失败
    3  没有失败，但至少一条**看不见**（这是给 CI 用的第三种结果）
    2  跑器自己出错（用法错误 / 检查文件加载失败）
"""

import argparse
import datetime
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pins  # noqa: E402 —— 钉住清单（2026-11-17）：fixture 之外的红名字清单

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

_REGISTRY = []


class Check:
    def __init__(self, name, asserts, fn):
        self.name = name
        self.asserts = asserts
        self.fn = fn


def check(name, asserts=""):
    """登记一个检查。函数返回：
        True / False
        (state, detail)   state 是 PASS / FAIL / UNKNOWN
        str               -> PASS，字符串当备注
    抛异常一律算 UNKNOWN——**检查自己坏了，不等于被检查的东西坏了**。
    """
    def deco(fn):
        _REGISTRY.append(Check(name, asserts, fn))
        return fn
    return deco


class _Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise _Timeout()


def run_one(c: Check, timeout_s: float):
    t0 = time.time()
    use_alarm = timeout_s and hasattr(signal, "SIGALRM")
    try:
        if use_alarm:
            signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, timeout_s)
        out = c.fn()
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if isinstance(out, tuple) and len(out) == 2:
            head, detail = out
            if head in (PASS, FAIL, UNKNOWN):
                state = head
            elif isinstance(head, bool):
                # 人会自然写成 (False, "为什么")，别把它当看不懂
                state = PASS if head else FAIL
            else:
                state, detail = UNKNOWN, f"状态看不懂：{head!r}"
        elif isinstance(out, bool):
            state, detail = (PASS if out else FAIL), ""
        elif isinstance(out, str):
            state, detail = PASS, out
        else:
            state, detail = UNKNOWN, f"检查返回了看不懂的东西：{out!r}"
    except _Timeout:
        state, detail = UNKNOWN, f"超时（{timeout_s:g}s）——没看到结果，不是看到没问题"
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa: BLE001 —— 连 SystemExit 也要兜：
        # 检查里 sys.exit(2) 是很常见的写法，不兜住的话一条坏检查会把整轮跑挂掉。
        state = UNKNOWN
        detail = f"检查自己抛了 {type(e).__name__}: {e}"
        if "--traceback" in sys.argv:
            traceback.print_exc()
    return {
        "name": c.name,
        "asserts": c.asserts,
        "state": state,
        "detail": detail,
        "ms": round((time.time() - t0) * 1000, 1),
    }


ICON = {PASS: "PASS", FAIL: "FAIL", UNKNOWN: "UNKNOWN"}


def report(rows, as_json, strict, fixture=None):
    counts = {s: 0 for s in (PASS, FAIL, UNKNOWN)}
    for r in rows:
        counts[r["state"]] += 1
    if as_json:
        payload = {"results": rows, "counts": counts}
        # 2026-11-09 11:1x：fixture 那一行原先是在 JSON 后面另起一行 print 的，
        # `--json` 的输出因此不再是单个 JSON（下游 json.loads 直接 Extra data）。
        # 自己的契约测试抓到的；fixture 结论必须并进同一个对象。
        if fixture is not None:
            meta = fixture[2] if len(fixture) > 2 else {}
            payload["fixture_leg"] = {"ok": fixture[0], "detail": fixture[1],
                                      "declared": meta.get("declared"),
                                      "observed": meta.get("observed"),
                                      # 2026-11-17：钉住清单也进机器可读的那份——
                                      # 收据不能只是人看的字符串。
                                      "pins_ok": meta.get("pins_ok"),
                                      "pins_sha": meta.get("pins_sha"),
                                      "pinned": meta.get("pinned"),
                                      "pins_missing": meta.get("pins_missing") or [],
                                      "pins_extra": meta.get("pins_extra") or []}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        width = max(len(r["name"]) for r in rows) if rows else 10
        for r in rows:
            print(f"  {ICON[r['state']]:7s}  {r['name']:{width}s}  {r['ms']:7.1f}ms  {r['detail']}")
        print()
        print("  " + "  ".join(f"{k} {counts[k]}" for k in (PASS, FAIL, UNKNOWN)))
        if fixture is not None:
            meta = fixture[2] if len(fixture) > 2 else {}
            counts_note = ""
            if meta.get("declared") is not None or meta.get("observed") is not None:
                counts_note = f"  [声明 {meta.get('declared')} / 观察 {meta.get('observed')}]"
            if meta.get("pinned") is not None:
                counts_note += (f"  [钉住 {meta.get('pinned')}"
                                f" / 缺 {len(meta.get('pins_missing') or [])}]")
            print(f"  fixture leg: {'OK  ' if fixture[0] else 'MISS'}  {fixture[1]}{counts_note}")
    if counts[FAIL] or (strict and counts[UNKNOWN]):
        return 1
    if counts[UNKNOWN]:
        return 3
    return 0


def load(path):
    # 跑器被 `python3 silent.py` 直接执行时，本模块叫 __main__；检查文件里
    # `from silent import check` 会**再导入一份**，注册表就分家了（第一次跑就踩到：
    # 「文件里没有 @check 登记的检查」）。把本模块塞进 sys.modules 的 "silent" 键。
    sys.modules.setdefault("silent", sys.modules[__name__])
    spec = importlib.util.spec_from_file_location("checks_under_test", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"加载不了检查文件：{path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture_leg(checkfile, timeout=300.0):
    """同目录的 test_<检查文件名>.py 必须在**这一轮**跑过，且退出 0。

    2026-11-07 Amelia 的尖点：fixture 停了和 fixture 跑了都长得像「没红」，
    所以红的证据要每一轮被观察到，而不是被推断。缺文件/非 0 退出都照实说。

    2026-11-08 rosetta 的尖点：`exit 0` 是**关于测试**的陈述，不是**关于红**的陈述——
    读者看不见「这轮有哪几条检查真的红过」，只能相信「有个文件通过了」。
    所以 fixture 每证明一条红，就往 stdout 打一行 `RED <检查名> <状态>: <理由>`，
    跑器把这行的条数和名字印出来。**没有 RED 行也是信息**，照实说。
    """
    d = os.path.dirname(os.path.abspath(checkfile))
    stem = os.path.splitext(os.path.basename(checkfile))[0]
    cand = os.path.join(d, "test_" + stem + ".py")
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    # 2026-11-09 17:1x bothireagent：声明的条数要能进机器可读的输出，
    # 这样「最后一次公开发布的那轮」本身就带着当时的声明数，成为对账物。
    meta = {"declared": None, "observed": None}
    if not os.path.exists(cand):
        return False, f"缺 test_{stem}.py —— 这一轮没有观察到检查会红（{stamp}）", meta
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, cand], cwd=d, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"test_{stem}.py 超时（{timeout:g}s，{stamp}）", meta
    dur = time.time() - t0
    # 2026-11-09 05:1x bothireagent：声明的条数变过就该被看见，否则「调低声明」不会留下痕迹。
    # 在测试文件旁边放一个 .decl.json，记上次的声明和测试文件的 sha256；不一致就把变化写进消息。
    # 11-09 10:5x 他的第二刀：sidecar 就躺在被描述的文件旁边，删掉它，下一轮看起来就是「首次运行」。
    # 所以另记一份 append-only 账本（默认 ~/.silent-decl-history.jsonl，SILENT_DECL_LEDGER 可指到别处）：
    # sidecar 没了但账本里有记录 → 按「记录缺失」报；EXPECT_REDS 从有到无 → 也按变化报。
    # 代价照实说：两处都删干净仍然看不见——这不是证明，是把最便宜的那条路堵上。
    decl_note = ""
    # 2026-11-17：reds / mcur 提前取出来——钉住清单比对要用到名字，声明对账也要用。
    reds = []
    names = []
    mcur = None
    if p.returncode == 0:
        out = p.stdout or ""
        # 计数按 RED **行**数（scrapling 的 fixture 里有两条同名红：声明 7 条、名字去重后 6 个）；
        # 钉住清单按名字（去重）——两件事，别混。
        reds = [l.strip()[4:] for l in out.splitlines() if l.strip().startswith("RED ")]
        names = pins.names_from_stdout(out)
        mcur = re.search(r"^EXPECT_REDS\s+(\d+)\s*$", out, re.M)
    last = None
    pins_sha = None
    try:
        import hashlib
        state = os.path.join(d, "." + os.path.basename(cand) + ".decl.json")
        test_sha = hashlib.sha256(open(cand, "rb").read()).hexdigest()[:12]
        prev = None
        if os.path.exists(state):
            prev = json.load(open(state, encoding="utf-8"))
        _pins, pins_sha = pins.load()
        ledger_path = (os.environ.get("SILENT_DECL_LEDGER")
                       or os.path.join(os.path.expanduser("~"), ".silent-decl-history.jsonl"))
        hist = []
        try:
            if os.path.exists(ledger_path):
                with open(ledger_path, encoding="utf-8") as f:
                    hist = [json.loads(line) for line in f if line.strip()]
        except Exception:
            hist = []
        target = os.path.abspath(cand)
        mine = [h for h in hist if h.get("path") == target]
        if not mine:  # 目录被拷到别处时，同名文件仍算同一个东西，但要在消息里说清
            mine = [h for h in hist if os.path.basename(h.get("path", "")) == os.path.basename(cand)]
        last = mine[-1] if mine else None
        if mcur and prev and prev.get("declared") is not None and prev["declared"] != int(mcur.group(1)):
            decl_note = (f"· **声明变了**：{prev['declared']} → {int(mcur.group(1))}"
                         f"（上次 {prev.get('at','?')}；测试文件 sha {prev.get('sha','?')} → {test_sha}）")
        elif mcur and not prev and last and last.get("declared") is not None:
            if last["declared"] != int(mcur.group(1)):
                decl_note = (f"· **声明记录缺失，按变化报**：sidecar 不见了；账本里上次是 {last['declared']}"
                             f"（{last.get('at','?')}），本轮读到 {int(mcur.group(1))}")
            else:
                decl_note = (f"· **声明记录缺失**：sidecar 不见了；账本里上次也是 {last['declared']}"
                             f"（{last.get('at','?')}）——读数没变，但这一层已经不是它自己在记了")
        elif not mcur and last and last.get("declared") is not None:
            decl_note = (f"· **声明不见了**：本轮没有 EXPECT_REDS 行；账本里上次是 {last['declared']}"
                         f"（{last.get('at','?')}）——从有到无也是变化")
        if mcur:
            json.dump({"declared": int(mcur.group(1)), "at": stamp, "sha": test_sha},
                      open(state, "w", encoding="utf-8"), ensure_ascii=False)
            with open(ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"path": target, "declared": int(mcur.group(1)), "at": stamp,
                                    "sha": test_sha, "pins_sha": pins_sha}, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — 这层只做提示，坏了不能让跑器挂
        decl_note = f"· 声明历史读写出错（{type(e).__name__}），本轮的计数没有对账"
    # 2026-11-17：钉住清单比对。EXPECT_REDS 只钉条数；把红 case A 换成 case B、条数不变，
    # 声明历史看不见。清单在 fixture 之外（pins.py），只钉名字，改它会进账本留痕。
    pins_note, pins_meta = pins.analyze(cand, names,
                                        prev_pins_sha=(last.get("pins_sha") if last else None))
    meta.update(pins_meta)
    decl_note += pins_note
    if p.returncode == 0:
        if pins_meta.get("pins_ok") is False:
            return False, (f"test_{stem}.py exit 0（{dur:.1f}s，observed {stamp}）"
                           f"**钉住的名字对不上**{decl_note}"), meta
        if mcur:
            want = int(mcur.group(1))
            meta["declared"], meta["observed"] = want, len(reds)
            if want != len(reds):
                return False, (f"test_{stem}.py exit 0，但**声明 {want} 条红、只观察到 {len(reds)} 条**"
                               f"（{dur:.1f}s，{stamp}）{decl_note}"), meta
            head = f"· 红 {len(reds)} 条（与声明的 {want} 条一致）"
        elif reds:
            head = f"· 红 {len(reds)} 条被观察到（**没有 EXPECT_REDS 声明**，计数不可对账）"
        else:
            meta["observed"] = 0
            return True, (f"test_{stem}.py exit 0（{dur:.1f}s，observed {stamp}）"
                          "· **没有 RED 行**：测试退出 0，但这一轮没报出任何红"), meta
        shown = "；".join(reds[:4]) + (f"；…共 {len(reds)} 条" if len(reds) > 4 else "")
        return True, f"test_{stem}.py exit 0（{dur:.1f}s，observed {stamp}）{head}：{shown}{decl_note}", meta
    tail = (p.stdout or "").strip().splitlines()[-1:] + (p.stderr or "").strip().splitlines()[-1:]
    return False, f"test_{stem}.py exit {p.returncode}（{dur:.1f}s，{stamp}）{' | '.join(tail)[:200]}", meta


def main():
    ap = argparse.ArgumentParser(description="三态检查跑器：pass / fail / unknown")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--json", action="store_true")
    r.add_argument("--strict", action="store_true", help="UNKNOWN 也算失败")
    r.add_argument("--timeout", type=float, default=60.0, help="每条检查的超时秒数")
    r.add_argument("--only", help="只跑名字里含这个子串的检查")
    r.add_argument("--require-fixtures", action="store_true",
                   help="没有观察到红色的 fixture 就算失败（CI 用）")
    pn = sub.add_parser("pin", help="把这一轮观察到的红名字写进 fixture 之外的钉住清单")
    pn.add_argument("file")
    pn.add_argument("--note", default="")
    pn.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args()

    if a.cmd == "pin":
        ok, msg, names = pins.pin(a.file, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                  note=a.note, timeout=a.timeout)
        print(("✓ " if ok else "✗ ") + msg)
        if names:
            print("  名字：" + "、".join(names))
        return 0 if ok else 2
    if a.cmd != "run":
        return 2
    try:
        load(a.file)
    except SystemExit as e:
        print(e)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"检查文件加载失败：{type(e).__name__}: {e}")
        return 2

    if not _REGISTRY:
        print("文件里没有 @check 登记的检查")
        return 2

    rows = []
    for c in _REGISTRY:
        if a.only and a.only not in c.name:
            continue
        rows.append(run_one(c, a.timeout))
    if not rows:
        print("--only 没匹配到任何检查")
        return 2
    ok, msg, meta = fixture_leg(a.file)
    code = report(rows, a.json, a.strict, fixture=(ok, msg, meta))
    if a.require_fixtures and not ok:
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())

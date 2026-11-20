"""pins.py — fixture 改不了的钉住清单（2026-11-17 建）。

问题：`EXPECT_REDS` 只钉条数。把红 case A 换成 case B、条数不变，
声明历史（sidecar + append-only 账本）看不见——它比的是数字，不是名字。

对策：在 fixture **之外**放一份 pins.json，记「这个 fixture 这一轮应该
被观察到哪几条红（按名字）」。每次跑把 pins.json 的 sha 记进账本；
清单被改了，下一轮会说出来。

代价照实说（写进设计里，不藏）：pins.json 和账本都是普通可写文件，
这不是密码学证明，只是把「悄悄换掉一条红 case」从零成本变成要动两份文件。

文件形状（默认 silent/pins.json，SILENT_PINS 可指到别处）：

    {
      "test_checks_site.py": {
        "dir": "silent",
        "pinned": ["feed/文章", "rss/时间"],
        "at": "2026-11-17 15:1x",
        "note": "首次钉住"
      }
    }

`dir` 是 checks 文件所在的目录名（同名 fixture 在不同目录时用来区分）；
拷到别的机器、目录改了，只留下「清单属于另一个目录」的提示，不会误判成红。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "pins.json")

# "RED <name> <STATE>: detail"（test_checks_continuity.py）和 "RED <name>: detail"
# （test_checks_site.py / test_checks_duami.py）两种格式都要认。
_STATE = re.compile(r"^(?P<name>.+?)\s+(PASS|FAIL|UNKNOWN)\s*:\s?(?P<detail>.*)$")
_PLAIN = re.compile(r"^(?P<name>[^:]+?)\s*:\s?(?P<detail>.*)$")


def path(arg=None):
    return arg or os.environ.get("SILENT_PINS") or DEFAULT


def load(arg=None):
    """返回 (dict, sha12 或 None)。坏文件当「没有清单」，不抛——这层只做提示。"""
    p = path(arg)
    try:
        raw = open(p, "rb").read()
    except OSError:
        return {}, None
    sha = hashlib.sha256(raw).hexdigest()[:12]
    try:
        data = json.loads(raw.decode("utf-8"))
        return (data if isinstance(data, dict) else {}), sha
    except (ValueError, UnicodeDecodeError):
        return {}, sha


def save(data, arg=None):
    p = path(arg)
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".pins.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]


def names_from_stdout(text):
    """从 fixture 的 stdout 里取出 `RED ...` 行的名字，按出现顺序去重。"""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.startswith("RED "):
            continue
        rest = s[4:].strip()
        m = _STATE.match(rest) or _PLAIN.match(rest)
        name = (m.group("name") if m else rest.split(":")[0]).strip()
        if name and name not in out:
            out.append(name)
    return out


def key_of(checkfile):
    """pins 的键：fixture 文件名（test_<stem>.py）。

    传 checks 文件或 fixture 文件都行——`analyze()` 拿到的是 fixture 路径，
    `pin()` 拿到的是 checks 路径，两边必须落到同一个键上（第一版就错在这：
    对 test_foo.py 又加了一次 test_ 前缀）。
    """
    b = os.path.basename(checkfile)
    if b.startswith("test_") and b.endswith(".py"):
        return b
    return "test_" + os.path.splitext(b)[0] + ".py"


def dir_of(checkfile):
    return os.path.basename(os.path.dirname(os.path.abspath(checkfile)))


def entry_of(data, checkfile):
    return data.get(key_of(checkfile))


def compare(pinned, observed):
    missing = [n for n in pinned if n not in observed]
    extra = [n for n in observed if n not in pinned]
    return missing, extra


def analyze(checkfile, observed, prev_pins_sha=None, arg=None):
    """生成 (note, meta)。meta 是机器可读的那份（进 --json 的 fixture_leg）。

    只在「清单里钉住的某条红这一轮没出现」时算失败（pins_ok=False）；
    多出来的红是信息，不是失败——但必须写出来，不然它就成了新的安静处。
    """
    data, sha = load(arg)
    e = entry_of(data, checkfile)
    meta = {"pins_ok": True, "pins_sha": sha, "pinned": None,
            "pins_missing": [], "pins_extra": []}
    if not e or not isinstance(e.get("pinned"), list):
        meta["pins_ok"] = None
        return ("· fixture 没有钉住清单（只钉了条数，没钉名字；`silent.py pin <检查文件>` 补上）",
                meta)
    if e.get("dir") and e["dir"] != dir_of(checkfile):
        meta["pins_ok"] = None
        return (f"· 钉住清单属于另一个目录（dir={e['dir']}），本目录没有钉住", meta)
    pinned = [str(n) for n in e["pinned"]]
    missing, extra = compare(pinned, observed)
    meta["pinned"] = len(pinned)
    meta["pins_missing"] = missing
    meta["pins_extra"] = extra
    notes = []
    if missing:
        meta["pins_ok"] = False
        notes.append(f"· **钉住清单有 {len(missing)} 条没被观察到**：{'、'.join(missing[:6])}"
                     + ("…" if len(missing) > 6 else "")
                     + "（fixture 被改了、还是检查退化了？要么修回来，要么改清单——改清单会留痕）")
    if extra:
        notes.append(f"· 新红未钉住：{'、'.join(extra[:6])}" + ("…" if len(extra) > 6 else "")
                     + "（先看是不是新 case；确认后用 pin 收进清单）")
    if not missing and not extra:
        notes.append(f"· 钉住 {len(pinned)} 条，全部观察到")
    if prev_pins_sha and sha and prev_pins_sha != sha:
        notes.append(f"· **钉住清单变了**：sha {prev_pins_sha} → {sha}（清单不在 fixture 里，改它要留下痕迹）")
    return ("".join(notes), meta)


def observe_reds(checkfile, timeout=300.0):
    """跑 fixture，返回 (returncode, stdout, stderr, reds)。给 `silent.py pin` 用。"""
    d = os.path.dirname(os.path.abspath(checkfile))
    cand = os.path.join(d, key_of(checkfile))
    if not os.path.exists(cand):
        return 2, "", f"缺 {os.path.basename(cand)}", []
    try:
        p = subprocess.run([sys.executable, cand], cwd=d, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 2, "", f"{os.path.basename(cand)} 超时（{timeout:g}s）", []
    return p.returncode, p.stdout or "", p.stderr or "", names_from_stdout(p.stdout)


def pin(checkfile, when, note="", arg=None, timeout=300.0):
    """把这一轮观察到的红名字写进清单。返回 (ok, message, names)。"""
    rc, out, err, reds = observe_reds(checkfile, timeout=timeout)
    if rc != 0:
        return False, f"fixture 退出 {rc}：{(err or out).strip().splitlines()[-1:] or ''}", reds
    if not reds:
        return False, "fixture 退出 0 但一条 RED 都没有——没有可钉的东西（先让它会红）", reds
    data, _sha = load(arg)
    old = entry_of(data, checkfile) or {}
    data[key_of(checkfile)] = {"dir": dir_of(checkfile), "pinned": reds,
                               "at": when, "note": note}
    new_sha = save(data, arg)
    changed = ""
    if old.get("pinned") and old["pinned"] != reds:
        gone = [n for n in old["pinned"] if n not in reds]
        added = [n for n in reds if n not in old["pinned"]]
        bits = []
        if gone:
            bits.append("去掉 " + "、".join(gone))
        if added:
            bits.append("加入 " + "、".join(added))
        changed = "（旧清单 → " + "；".join(bits) + "）"
    return True, f"钉住 {len(reds)} 条（sha {new_sha}）{changed}", reds

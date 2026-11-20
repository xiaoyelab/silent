"""library.py — 可复用的「静默失败」判据（纯函数，不碰网络）。

为什么有（2026-11-06）：四单下来，每单都在重写同一类断言——键唯一、计数对不上、
空字段和缺字段同形、参数被悄悄丢掉。把它们抽成零件，下一单直接用，
检查文件里只写「取哪份数据、用哪条判据」。

约定：每个函数收纯数据，返回 `(ok: bool | None, detail: str)`；
`None` 表示「判不了」（数据不够），由调用方映射成 UNKNOWN。
"""

from collections import Counter


def key_unique(rows, key):
    """分组键必须唯一。2026-11-06 duami 实测：两个 agent 同名 LeonBot，
    按 name 分组把两个状态交织成 43 次假翻转。"""
    vals = [r.get(key) for r in rows]
    dup = {v: n for v, n in Counter(vals).items() if v is not None and n > 1}
    if dup:
        top = list(dup.items())[:3]
        return False, f"{len(dup)} 个 {key} 重复，例：{top}"
    return True, f"{len(rows)} 行，{key} 唯一"


def counts_add_up(declared, actual, label=""):
    """两处各自维护的计数必须对得上。2026-11-06 aideprecations 实测：
    sources[].rows 声明 185/43/58/52，实际 179/36/55/51。

    2026-11-07 自己栽过：调用方用 `{"feed": n}` 对 `{"posts": m}`，两边没有共同的键，
    循环一次都没进就返回 True——「没比」被当成「比过了」。现在没有共同键 = 判不了。"""
    shared = set(declared) & set(actual)
    if not shared:
        return None, f"两边没有共同的键（{sorted(declared)} vs {sorted(actual)}），判不了"
    bad = []
    for k, d in declared.items():
        a = actual.get(k)
        if d is None or a is None:
            continue
        if d != a:
            bad.append(f"{k}: 声明 {d} / 实际 {a}")
    if bad:
        return False, ("；".join(bad) if not label else f"{label}：" + "；".join(bad))
    return True, f"{len(declared)} 个计数一致"


def done_not_over_total(done, total, label="done/total"):
    """进度不能超过总量。2026-11-06 scraplingdata 实测：projects_done 9908 > total 9904。"""
    if done is None or total is None:
        return None, f"{label} 缺数（done={done}, total={total}）"
    if done > total:
        return False, f"{label}: {done} > {total}（超 {done - total}）"
    return True, f"{label}: {done} ≤ {total}"


def field_states(rows, field, required=False):
    """同一列的空要分三态：有值 / 空值 / 键都不在。
    契约说 required 时，`absent` 就是违约，不能当成「本来没有」。"""
    present = empty = absent = 0
    for r in rows:
        if field not in r:
            absent += 1
        elif r[field] in (None, "", [], {}):
            empty += 1
        else:
            present += 1
    detail = f"{field}: 有值 {present} / 空值 {empty} / 键缺失 {absent}"
    if required and absent:
        return False, detail + "（契约说 required，缺失即违约）"
    if present == 0 and absent == 0:
        return None, detail + "（整列都空，无法区分路由丢字段还是本来没有）"
    return True, detail


def param_echo(sent, echoed):
    """发出去的参数必须被回显/应用。2026-11-05 实测：`limit` 被静默吃掉，
    返回默认 20 条，调用方以为拿到了全部。"""
    lost = [k for k, v in sent.items() if echoed.get(k) != v]
    if lost:
        return False, f"这些参数没生效：{lost}（发出 {sent}，回显 {echoed}）"
    return True, f"{len(sent)} 个参数都回显了"


def same_second_cluster(timestamps, within_s=5):
    """多张卡的 last_heartbeat 落在同一秒级窗口 → 更像同一个操作者，不是平台 ingest。
    （2026-11-06 duami：3 张卡 14:56:33/31/33。）"""
    ts = sorted(t for t in timestamps if t is not None)
    for i in range(len(ts) - 1):
        group = [t for t in ts[i:] if (t - ts[i]).total_seconds() <= within_s]
        if len(group) >= 2:
            return True, f"{len(group)} 个时间戳落在 {within_s}s 内 → 疑似同一操作者"
    return False, "没有同秒聚簇"


INSTR_KEYS = {"approval_request", "approve_request", "budget_request",
              "payment_request", "action_required", "next_action"}
_INSTR_RE = __import__("re").compile(r"approv\w*[^.\n]{0,40}\bbudget\b", __import__("re").I)


def _embedded(s):
    """字符串里藏着的 JSON / base64(JSON)。Sunny 2026-11-07：要求扫描能到达内嵌一层。"""
    import base64
    import json
    t = s.strip()
    if not t:
        return None
    if t[:1] in "{[":
        try:
            return json.loads(t)
        except Exception:  # noqa: BLE001
            pass
    if len(t) >= 40 and len(t) % 4 == 0 and __import__("re").fullmatch(r"[A-Za-z0-9+/]+={0,2}", t):
        try:
            dec = base64.b64decode(t).decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
        if dec.strip()[:1] in "{[":
            try:
                return json.loads(dec)
            except Exception:  # noqa: BLE001
                return None
    return None


def _scan(body, keys, regex, max_depth=8):
    """返回 [(路径, 深度)]；路径带（文本）（内嵌）标记，深度给人看。"""
    hits = []

    def walk(x, path="", depth=0):
        if depth > max_depth:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                p = f"{path}.{k}" if path else k
                keyhit = k.lower() in keys and isinstance(v, (str, dict, list))
                if keyhit:
                    hits.append((p, depth + 1))
                if isinstance(v, str):
                    if not keyhit and regex.search(v):
                        hits.append((p + "（文本）", depth + 1))
                    emb = _embedded(v)
                    if emb is not None:
                        walk(emb, p + "（内嵌）", depth + 1)
                else:
                    walk(v, p, depth + 1)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]", depth + 1)

    walk(body)
    return hits


def _hits_detail(hits):
    return ", ".join(f"{p}（depth={d}）" for p, d in hits[:3])


def no_instruction_payload(body):
    """数据/错误响应体里不该出现「请批准预算 / 请付款」这类对消费方的指令。

    2026-11-07 scraplingdata 实测：429 体里带 approval_request，
    原文「Approve a small budget (e.g. $1)?」——错误路径恰好是 agent 最可能照做的地方。
    Sunny 补：扫描要能到内嵌一层（JSON 字符串、base64），且失败要报深度。
    """
    if not isinstance(body, (dict, list)):
        return None, "响应体不是对象/数组，判不了"
    hits = _scan(body, INSTR_KEYS, _INSTR_RE)
    if hits:
        return False, "响应体里有对消费方的指令/授权请求：" + _hits_detail(hits)
    return True, "响应体里没有指令性字段"


PAY_HINT_KEYS = {"approval_request", "payment_request", "budget_request",
                 "x402", "accepts", "payment_required"}
_PAY_RE = __import__("re").compile(r"x402|approv\w*[^.\n]{0,40}\bbudget\b|pay\w* (?:this|for this)", __import__("re").I)


def _x402_terms(body):
    """402 体里必须有 x402 条款：x402Version + accepts[]（scheme/network/amount）。

    2026-11-07 实测真样本（scraplingdata 付费路由）：
    {"x402Version":2,"accepts":[{"scheme":"exact","network":"eip155:8453",
     "amount":"3000","maxAmountRequired":"3000",...}]}
    """
    if not isinstance(body, dict):
        return False
    if isinstance(body.get("x402Version"), (int, str)):
        return True
    acc = body.get("accepts")
    if isinstance(acc, list) and acc and isinstance(acc[0], dict):
        a = acc[0]
        return all(k in a for k in ("scheme", "network")) and ("amount" in a or "maxAmountRequired" in a)
    return False


def payment_ask_outside_402(status, body):
    """付款请求只该出现在 402 上，而且 402 要带 x402 条款。

    kleinbot（2026-11-07）：x402 就是 HTTP 402；把购买邀约塞进 429，是给限流文案
    钉了一条销售话术。调用方该按状态码决定，不该按错误体里的散文决定。
    """
    if not isinstance(body, (dict, list)):
        return None, "响应体不是对象/数组，判不了"
    terms = _x402_terms(body)
    if str(status) == "402":
        if terms:
            return True, "402 + x402 条款"
        return False, "402 但没有 x402 条款（缺 x402Version/accepts/scheme/network/amount）"
    hits = _scan(body, PAY_HINT_KEYS, _PAY_RE)
    if terms:
        return False, f"x402 付款条款出现在 HTTP {status}，不在 402"
    if hits:
        return False, f"付款请求出现在 HTTP {status} 上，不在 402：" + _hits_detail(hits)
    return True, "没有付款请求"


def data_freshness(as_of, window_s, now=None):
    """观察到了，但数据比窗口旧 → 不是「通过」，是「过期」。

    2026-11-07 读了 Fork p/1038（bradley-work「监控需要四个结果」）：
    CHANGED / UNCHANGED / UNKNOWN / STALE。我的三态里，STALE 会被算成 PASS，
    因为计数自洽、字段都在——只是那份数据 16 小时前的。
    """
    import datetime as _dt
    if not as_of:
        return None, "没有 as_of，判不了新鲜度"
    try:
        t = _dt.datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except ValueError:
        return None, f"as_of 解析不了：{as_of!r}"
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    age = (now - t).total_seconds()
    if age < 0:
        return None, f"as_of 在未来（{as_of}），判不了"
    if age > window_s:
        return False, f"数据 {int(age // 60)} 分钟前的，超过窗口 {int(window_s // 60)} 分钟（as_of {as_of}）"
    return True, f"数据 {int(age // 60)} 分钟内（as_of {as_of}）"

#!/usr/bin/env python3
"""案例 1–3 的可跑复现（外部平台的形状，用假数据模拟）。

三条记录都来自真实案例（`CASES.md` 1–3），去掉平台名字，只留形状：

9001 帖子：评论里买家写「filled and closed」，`status` 仍是 open、`closed_at` 是 null。
9002 任务：`expiryTime` 已过去很多天，`status` 仍是 open、仍可提交。
9003 付费任务：评论说已释放结算，`accepting_submissions` 仍是 true。

两种消费者：
- naive：只读 `status` → 报「3 条可做」。
- checker：评论/时间与状态字段交叉读 → 报 3 条漂移。

跑 `python3 demo.py`：退出 0 = 复现成立（naive 说可做，checker 说已经关了）。
"""
import datetime

NOW = datetime.datetime(2026, 11, 21, 7, 0)

RECORDS = [
    {
        "id": "9001", "kind": "post", "status": "open", "closed_at": None,
        "comments": ["2026-11-09T08:15Z buyer: this bounty is filled and closed"],
    },
    {
        "id": "9002", "kind": "task", "status": "open",
        "expiryTime": "2026-11-06T00:00:00Z", "comments": [],
    },
    {
        "id": "9003", "kind": "paid_task", "status": "open", "accepting_submissions": True,
        "closed_at": None,
        "comments": ["2026-11-10T12:00Z buyer: released and settled"],
    },
]

CLOSED_WORDS = ("filled and closed", "released and settled", "settled", "closed")


def naive_open(records):
    """只信 status 字段的消费者。"""
    return [r["id"] for r in records if r.get("status") == "open"]


def status_drift(records, now=NOW):
    """交叉读：评论/期限/closed_at 与 status 是否一致。返回 [(id, 理由)]。"""
    out = []
    for r in records:
        said_closed = any(w in c.lower() for c in r.get("comments", []) for w in CLOSED_WORDS)
        if r.get("status") == "open" and said_closed:
            out.append((r["id"], "评论宣告已关闭，status 仍是 open / closed_at 为空"))
        if r.get("status") == "open" and r.get("expiryTime"):
            exp = datetime.datetime.fromisoformat(r["expiryTime"].replace("Z", "+00:00")).replace(tzinfo=None)
            if exp < now:
                out.append((r["id"], f"已过期（{exp:%Y-%m-%d}），status 仍是 open"))
        if r.get("kind") == "paid_task" and said_closed and r.get("accepting_submissions"):
            out.append((r["id"], "已结算，accepting_submissions 仍是 true"))
    return out


def main():
    naive = naive_open(RECORDS)
    drift = status_drift(RECORDS)
    print(f"naive（只读 status）：{len(naive)} 条可做 {naive}")
    for rid, why in drift:
        print(f"  漂移 {rid}: {why}")
    reproduced = len(naive) == 3 and len(drift) >= 3
    print("复现成立" if reproduced else "没复现")
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())

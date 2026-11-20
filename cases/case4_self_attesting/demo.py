#!/usr/bin/env python3
"""案例 4 的可跑复现：校验器自己给自己发合格证。

构造：一个 pack 进程把数据写了一半（模拟写入时截断），**然后对已经截断的字节算哈希**；
verify 再拿同一批字节重算、与那个哈希比 —— 一致，于是打印「通过」。
独立见证（另一个进程按约定读内容：期望 10 块，实际 5 块）说它坏了。

跑 `python3 demo.py`：退出 0 = 复现成立（自证 PASS + 独立见证 FAIL 同时出现）。
"""
import hashlib
import json
import os
import pathlib
import tempfile


def pack(d, blocks=10, truncate_at=5):
    """写数据，然后对「实际写下去的字节」算哈希——截断就发生在算哈希之前。"""
    data = b"".join(b"BLOCK-%02d\n" % i for i in range(blocks))
    written = data[: len(b"BLOCK-00\n") * truncate_at]      # 模拟写了一半
    p = pathlib.Path(d) / "snapshot.bin"
    p.write_bytes(written)
    h = hashlib.sha256(p.read_bytes()).hexdigest()          # 同一个进程、同一批字节
    (pathlib.Path(d) / "snapshot.bin.sha256").write_text(h + "\n", encoding="utf-8")
    (pathlib.Path(d) / "manifest.json").write_text(json.dumps({"blocks": blocks}), encoding="utf-8")


def verify_self_attesting(d):
    """只核对「写入后字节没变」——这正是只能自证的形状。"""
    d = pathlib.Path(d)
    h = hashlib.sha256((d / "snapshot.bin").read_bytes()).hexdigest()
    want = (d / "snapshot.bin.sha256").read_text(encoding="utf-8").strip()
    return h == want, "sha256 校验通过"


def verify_independent(d):
    """另一个进程按约定读内容：manifest 说应有几块，就数几块。"""
    d = pathlib.Path(d)
    want = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["blocks"]
    got = len([ln for ln in (d / "snapshot.bin").read_text(encoding="utf-8").splitlines() if ln.strip()])
    return got == want, f"manifest 期望 {want} 块，实际 {got} 块"


def main():
    with tempfile.TemporaryDirectory() as d:
        pack(d)
        ok1, msg1 = verify_self_attesting(d)
        ok2, msg2 = verify_independent(d)
        print(f"自证校验: {'PASS' if ok1 else 'FAIL'} · {msg1}")
        print(f"独立见证: {'PASS' if ok2 else 'FAIL'} · {msg2}")
        reproduced = ok1 and not ok2
        print("复现成立" if reproduced else "没复现（构造错了）")
        return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())

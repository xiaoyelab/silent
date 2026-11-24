#!/usr/bin/env python3
"""案例 6 的可跑复现：合成成功退出，产物是 0.011 秒的静音。

2026-11-24 实测（macOS 26.7.1）：`say -v <未下载的嗓音> -o out.aiff "…"` **退出码 0**，
产物 0.011519 秒。文件名对、格式对、能播——播出来什么都没有。整条流水线继续往下走，
字幕、封面、成片都"成功"。

这里不依赖 macOS 的 `say`：用 stdlib 造一个**又短又全零**的 wav，形状一样。
两个检查器读它：
- 坏的：只看「文件在、不是空的」→ 报 ok。
- 好的：读时长和峰值 → 报「没有内容」和「全零」。

跑 `python3 demo.py`：退出 0 = 复现成立（坏的说 ok，好的报 2 条）。
"""
import array
import os
import sys
import tempfile
import wave

RATE = 44100
SHORT = 508 / RATE        # 实测值：say 给没下载的嗓音 = 508 帧 = 0.011519s
PEAK_MIN = 200            # 200/32767 ≈ -44 dBFS；低于它当静音
DUR_MIN = 0.2


def synth(path, seconds, amp=0):
    n = max(1, int(RATE * seconds))
    data = array.array("h", [amp] * n)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    return path


def buggy_ok(path):
    """最常见的那条检查：文件存在、大小不为 0。"""
    return os.path.exists(path) and os.path.getsize(path) > 44


def inspect(path):
    with wave.open(path, "rb") as w:
        n, rate = w.getnframes(), w.getframerate()
        raw = w.readframes(n)
    samples = array.array("h")
    samples.frombytes(raw)
    return {"dur": (n / rate) if rate else 0.0,
            "peak": max((abs(s) for s in samples), default=0),
            "rate": rate}


def good_problems(path):
    f = inspect(path)
    out = []
    if f["dur"] < DUR_MIN:
        out.append("时长 %.6fs < %.1fs：没有内容" % (f["dur"], DUR_MIN))
    if f["peak"] < PEAK_MIN:
        out.append("峰值 %d/32767：全零或接近静音" % f["peak"])
    return out


def main():
    d = tempfile.mkdtemp(prefix="case6-")
    bad = synth(os.path.join(d, "vo.wav"), SHORT)
    good = synth(os.path.join(d, "vo-real.wav"), 2.0, amp=8000)
    print("短静音 : 坏检查 %s / 好检查 %s" % (
        "ok" if buggy_ok(bad) else "fail", good_problems(bad) or "ok"))
    print("正常音 : 坏检查 %s / 好检查 %s" % (
        "ok" if buggy_ok(good) else "fail", good_problems(good) or "ok"))
    reproduced = buggy_ok(bad) and good_problems(bad) and not good_problems(good)
    print("复现成立" if reproduced else "构造错了：短静音没被拦住，或正常音被误拦")
    return 0 if reproduced else 1


if __name__ == "__main__":
    sys.exit(main())

"""demo_checks.py — 跑器自测用的检查集：四种结果各一条。

    python3 silent.py run demo_checks.py            # 期望 exit 1（里面有一 fail）
    python3 silent.py run demo_checks.py --only ok  # 期望 exit 0
    python3 silent.py run demo_checks.py --only boom --json
    python3 silent.py run demo_checks.py --only slow --timeout 0.3   # 期望 exit 3
"""

import sys
import time

from silent import check, UNKNOWN, PASS, FAIL  # noqa: F401


@check("ok", "这一条应该通过")
def _ok():
    return True


@check("nope", "这一条应该失败")
def _nope():
    return False, "看到的是旧的：status_since 比 last_heartbeat_at 早 12 秒"


@check("boom", "检查自己抛异常 → 必须是 unknown，不是 fail")
def _boom():
    raise RuntimeError("上游 503")


@check("garbage", "返回值看不懂 → unknown")
def _garbage():
    return {"weird": "shape"}


@check("slow", "超时 → unknown，不是 fail")
def _slow():
    time.sleep(5)


@check("explicit-unknown", "检查自己声明看不见")
def _unknown():
    return UNKNOWN, "没有读权限，这一条判断不了"


@check("usage-error", "故意用错参数（不应影响别的检查）")
def _usage():
    sys.exit(2)  # SystemExit 不是 Exception 的子类，跑器要把它兜成 unknown


if __name__ == "__main__":
    print("这个文件不直接跑，用 silent.py run demo_checks.py")

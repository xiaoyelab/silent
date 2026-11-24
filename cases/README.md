# 案例：可跑的静默失败复现

完整叙述（来源、判据、反例行、证据等级）在上一层 [`CASES.md`](../CASES.md)。
这里只放**能一条命令跑出来的复现**——案例 1–3 依赖外部平台的实时数据，只能按 `CASES.md` 里的命令在线复现；案例 4、5 是本机形状，做成了自包含的玩具。

| 案例 | 目录 | 一条命令 | 复现什么 |
|---|---|---|---|
| 1–3 | `case1_3_status_drift/` | `python3 case1_3_status_drift/demo.py` | 评论/期限说已关闭，`status` 仍 open → 只读 status 的消费者报 3 条可做 |
| 4 | `case4_self_attesting/` | `python3 case4_self_attesting/demo.py` | 写一半的数据 + 同进程哈希 → 自证校验 PASS，独立见证 FAIL |
| 5 | `case5_never_matches/` | `python3 case5_never_matches/demo.py` | 检查器匹配一个不存在的模式 → 命中 0 行，报「干净」 |
| 6 | `case6_exit_zero_silence/` | `python3 case6_exit_zero_silence/demo.py` | 合成退出 0，产物 0.011 秒静音 → 只看「文件在」的检查报 ok |

案例 1–3 本来依赖外部平台的实时数据（`CASES.md` 里保留了当时的 API 输出）；这里用**假数据保留形状**，
不冒充实时：跑出来的东西证明的是「这种漂移会被漏掉」，不是「今天平台上还有这三条」。

三个本机 demo 的退出码是**反着的**：0 = 复现成立（坏的样子出现了），1 = 构造错了。
这不是检查器的三态，是「案例还在不在」的开关。

```bash
python3 test_cases.py     # 三个复现 + 反例（把构造修好，复现就必须不再成立）
```

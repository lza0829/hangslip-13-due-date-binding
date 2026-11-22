"""取衣日改约全链路正确性测试（自包含，不依赖 pytest）。

覆盖：
1. 改约后挂牌/扫描/待取排序/隔离预检/总览徽章只认新日子
2. 已取/已隔离禁改、原因必填、非法日期、同日拒绝
3. 同事务回滚：流水写入失败时 due_date 不变、无残留
4. 并发两人改同一票串行化、改约与超期隔离不双判
5. 结案后改约被事务内权威检查拒绝（无旁路）
"""

from __future__ import annotations

import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="hangslip-test-"))
import app.config as cfg  # noqa: E402

cfg.DB_PATH = _tmp / "test.db"

import app.db as dbmod  # noqa: E402

dbmod.DB_PATH = cfg.DB_PATH
from app.db import connect, init_db, transaction  # noqa: E402
from app.services import due, tickets  # noqa: E402
from app.services.gate import seal_day, today_str  # noqa: E402
from fastapi import HTTPException  # noqa: E402

TODAY = today_str()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXTWEEK = (date.today() + timedelta(days=7)).isoformat()

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def expect_http(name: str, status: int, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        check(name, False, f"未抛出，期望 {status}")
    except HTTPException as e:
        check(name, e.status_code == status, f"得到 {e.status_code} 期望 {status}：{e.detail}")


def make_ticket(no: str, due: str, status: str = "已收") -> None:
    now = "2026-01-01 09:00:00"
    with transaction() as conn:
        conn.execute(
            """INSERT INTO hang_tickets
               (ticket_no, store_code, pickup_code, customer_name, status, opened_at, due_date)
               VALUES (?,?,?,?,?,?,?)""",
            (no, "店-河西", "暗码", f"顾客{no}", status, now, due),
        )
        conn.execute(
            "INSERT INTO ticket_items(ticket_no, garment, qty) VALUES (?,?,?)",
            (no, "衬衣", 1),
        )


init_db()
with transaction() as conn:
    conn.execute(
        "INSERT INTO stores(code, name, rack_count, active) VALUES (?,?,?,1)",
        ("店-河西", "河西干洗", 3),
    )

print("== 1. 改约全链路只认新日子 ==")
make_ticket("挂-T1", YESTERDAY, "待取")
t = tickets.get_ticket("挂-T1")
check("改前：详情标记超期", t["超期"] is True)
conn = connect()
check("改前：命中超期扫描", any(r["ticket_no"] == "挂-T1" for r in due.list_overdue(conn)))
check("改前：总览超期计数=1", due.count_overdue(conn) == 1)
conn.close()

due.reschedule("挂-T1", TOMORROW, "顾客来电延期")
t = tickets.get_ticket("挂-T1")
check("改后：due_date 落为新日", t["due_date"] == TOMORROW)
check("改后：不再超期", t["超期"] is False)
check("改后：改日流水挂 1 条", len(t["改日流水"]) == 1)
v = t["改日流水"][0]
check(
    "流水记旧日→新日+原因",
    v["old_due_date"] == YESTERDAY and v["new_due_date"] == TOMORROW and v["reason"] == "顾客来电延期",
)
check("改后：工序事件留痕", any("改约取衣日" in e["note"] for e in t["events"]))
conn = connect()
check("改后：离开超期扫描", not any(r["ticket_no"] == "挂-T1" for r in due.list_overdue(conn)))
check("改后：总览超期计数=0", due.count_overdue(conn) == 0)
conn.close()
expect_http("改后：未逾新日，超期隔离被预检拒绝", 409, tickets.quarantine, "挂-T1", "超期隔离", "x")

print("== 2. 待取页按取衣日升序（最早该取在前） ==")
make_ticket("挂-T2", NEXTWEEK, "待取")
make_ticket("挂-T3", YESTERDAY, "待取")
ready = tickets.list_tickets(status="待取")
order = [r["ticket_no"] for r in ready]
check(
    "排序：昨日票 T3 先于明日票 T1 先于下周票 T2",
    order.index("挂-T3") < order.index("挂-T1") < order.index("挂-T2"),
    str(order),
)
due.reschedule("挂-T3", NEXTWEEK, "再次延期")
ready = tickets.list_tickets(status="待取")
order = [r["ticket_no"] for r in ready]
check("改约后排序跟随新日（T3 沉到 T2 同档）", order.index("挂-T1") < order.index("挂-T3"), str(order))
check("列表超期标记与谓词同源", all(r["超期"] == (r["due_date"] < TODAY) for r in ready))

print("== 3. 禁改与入参校验 ==")
make_ticket("挂-T4", TODAY, "待取")
tickets.pickup("挂-T4", "暗码")
expect_http("已取票禁改", 409, due.reschedule, "挂-T4", TOMORROW, "试改")
make_ticket("挂-T5", YESTERDAY, "待取")
tickets.quarantine("挂-T5", "超期隔离", "逾承诺日未取")
expect_http("超期隔离票禁改", 409, due.reschedule, "挂-T5", TOMORROW, "试改")
expect_http("原因必填", 400, due.reschedule, "挂-T2", TOMORROW, "  ")
expect_http("非法日期", 400, due.reschedule, "挂-T2", "2026/02/30", "原因")
expect_http("票不存在", 404, due.reschedule, "挂-NOPE", TOMORROW, "原因")
cur_due = tickets.get_ticket("挂-T2")["due_date"]
expect_http("新旧同日拒绝", 409, due.reschedule, "挂-T2", cur_due, "原因")

print("== 4. 同事务回滚（流水写入失败整笔回滚） ==")
make_ticket("挂-T2b", NEXTWEEK, "待取")
from contextlib import contextmanager  # noqa: E402

boom = {"on": True}


class FailingConn:
    """连接代理：改日流水 INSERT 时注入故障，其余透传。"""

    def __init__(self, real):
        self._r = real

    def execute(self, sql, params=()):
        if boom["on"] and "INSERT INTO due_date_versions" in sql:
            raise RuntimeError("模拟流水写入失败")
        return self._r.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._r, name)


real_transaction = due.transaction


@contextmanager
def failing_transaction():
    with real_transaction() as conn:
        yield FailingConn(conn)


due.transaction = failing_transaction
rolled_back = False
try:
    due.reschedule("挂-T2b", TOMORROW, "回滚验证")
except RuntimeError:
    rolled_back = True
finally:
    due.transaction = real_transaction
    boom["on"] = False
check("流水失败时整笔报错并回滚", rolled_back)
t = tickets.get_ticket("挂-T2b")
check("回滚：due_date 维持旧日", t["due_date"] == NEXTWEEK)
check("回滚：无残留流水", len(t["改日流水"]) == 0)
check("回滚：无残留工序事件", not any("改约取衣日" in e["note"] for e in t["events"]))

print("== 5. 并发两人改同一票：串行化、无半笔 ==")
make_ticket("挂-T6", TODAY, "待取")
errors: list[Exception] = []
lock = threading.Lock()


def worker(no: str, target: str):
    try:
        due.reschedule(no, target, f"并发店员{target}")
    except HTTPException as e:
        with lock:
            errors.append(e)


t1 = threading.Thread(target=worker, args=("挂-T6", TOMORROW))
t2 = threading.Thread(target=worker, args=("挂-T6", NEXTWEEK))
t1.start(); t2.start(); t1.join(); t2.join()
check("并发改约无异常", errors == [], [str(e) for e in errors])
t = tickets.get_ticket("挂-T6")
check("并发后只有一个权威 due_date", t["due_date"] in (TOMORROW, NEXTWEEK))
check("两次改约各留一条流水", len(t["改日流水"]) == 2, str(len(t["改日流水"])))
# 流水链新旧衔接、字段与权威日一致
chain = sorted(t["改日流水"], key=lambda x: x["id"])
linked = all(chain[i]["new_due_date"] == chain[i + 1]["old_due_date"] for i in range(len(chain) - 1))
check("流水链式衔接", linked)
check("末条流水新日=权威 due_date", chain[-1]["new_due_date"] == t["due_date"])

print("== 6. 并发改约 vs 超期隔离：不双判 ==")
make_ticket("挂-T7", YESTERDAY, "待取")
outcomes = {"quar_ok": 0, "quar_rej": 0, "resc_ok": 0, "resc_rej": 0, "other": 0}
olock = threading.Lock()


def qworker():
    try:
        tickets.quarantine("挂-T7", "超期隔离", "扫描隔离")
        with olock:
            outcomes["quar_ok"] += 1
    except HTTPException as e:
        with olock:
            if e.status_code == 409:
                outcomes["quar_rej"] += 1
            else:
                outcomes["other"] += 1


def rworker(target: str):
    try:
        due.reschedule("挂-T7", target, "并发改约")
        with olock:
            outcomes["resc_ok"] += 1
    except HTTPException as e:
        with olock:
            if e.status_code == 409:
                outcomes["resc_rej"] += 1
            else:
                outcomes["other"] += 1


threads = [
    threading.Thread(target=qworker),
    threading.Thread(target=rworker, args=(NEXTWEEK,)),
    threading.Thread(target=qworker),
    threading.Thread(target=rworker, args=(TOMORROW,)),
    threading.Thread(target=qworker),
]
for th in threads:
    th.start()
for th in threads:
    th.join()
check("无 409 以外的异常", outcomes["other"] == 0, str(outcomes))
check("隔离至多成功一次", outcomes["quar_ok"] <= 1, str(outcomes))
final = tickets.get_ticket("挂-T7")
if final["status"] == "超期隔离":
    check("隔离赢家路径：后续改约全部被拒", outcomes["resc_rej"] >= 1 and outcomes["resc_ok"] == 0, str(outcomes))
    check("终态=超期隔离且不再出现在超期扫描", final["status"] == "超期隔离")
else:
    check("改约赢家路径：隔离全部被拒（未逾新日）", outcomes["quar_ok"] == 0 and outcomes["quar_rej"] >= 1, str(outcomes))
    check("终态仍待取且权威日为改约后日期", final["status"] == "待取" and final["due_date"] in (TOMORROW, NEXTWEEK))
conn = connect()
scan_t7 = [r for r in due.list_overdue(conn) if r["ticket_no"] == "挂-T7"]
conn.close()
check("扫描与终态口径一致（待取且昨日才在清单）", (scan_t7 != []) == (final["status"] == "待取" and final["due_date"] < TODAY))

print("== 7. 结案日闸：事务内权威检查拒绝旁路 ==")
make_ticket("挂-T8", TODAY, "待取")
seal_day(note="测试结案")
expect_http("结案后改约被拒", 409, due.reschedule, "挂-T8", TOMORROW, "旁路尝试")
check("被拒后 due_date 未动", tickets.get_ticket("挂-T8")["due_date"] == TODAY)
expect_http("结案后开票被拒", 409, tickets.create_ticket, {
    "ticket_no": "挂-T9", "store_code": "店-河西", "pickup_code": "x",
    "customer_name": "c", "due_date": TODAY, "items": [{"garment": "衬衣", "qty": 1}],
})
expect_http("结案后取衣核销被拒", 409, tickets.pickup, "挂-T8", "暗码")

print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
raise SystemExit(1 if FAIL else 0)

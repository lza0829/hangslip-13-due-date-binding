"""取衣日统一口径（全局唯一权威：hang_tickets.due_date）。

架构口径：店员可改约为准。
- 挂牌展示、待取排序、超期扫描、隔离预检、总览超期徽章一律只认 due_date。
- due_date_versions 仅为改约审计流水，不参与任何业务判定。
- 统一超期谓词 OVERDUE_WHERE 被扫描清单、隔离预检、总览徽章共用，杜绝三处各认各的日子。
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException

from app.db import transaction
from app.services.gate import ensure_day_row, today_str

# 唯一超期口径：处于「待取」且承诺取衣日早于今天。
# 已取/已隔离的票不再计入超期；自动隔离另立需求，本模块不改变票态。
OVERDUE_WHERE = "status = '待取' AND due_date < ?"

# 允许改约的票态：未取衣且未隔离。
RESCHEDULABLE_STATUSES = ("已收", "水洗", "烘干", "熨烫", "待取")
TERMINAL_STATUSES = ("已取", "超期隔离", "丢失隔离")


def _validate_iso_date(value: str, field: str) -> str:
    value = (value or "").strip()
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, f"{field}须为 YYYY-MM-DD 日期") from exc
    return value


def list_overdue(conn, day: str | None = None) -> list[dict]:
    """超期扫描清单：只认当前 due_date，与隔离预检/总览共用同一谓词。"""
    d = day or today_str()
    return [
        dict(r)
        for r in conn.execute(
            f"""SELECT ticket_no, store_code, customer_name, due_date, status
                FROM hang_tickets WHERE {OVERDUE_WHERE}
                ORDER BY due_date ASC, id ASC""",
            (d,),
        ).fetchall()
    ]


def count_overdue(conn, day: str | None = None) -> int:
    d = day or today_str()
    return conn.execute(
        f"SELECT COUNT(*) AS c FROM hang_tickets WHERE {OVERDUE_WHERE}", (d,)
    ).fetchone()["c"]


def row_is_overdue(row: dict, day: str | None = None) -> bool:
    """行级超期判定，条件与 OVERDUE_WHERE 严格同源，供挂牌序列化复用。"""
    d = day or today_str()
    return row.get("status") == "待取" and row["due_date"] < d


def list_due_versions(ticket_no: str | None = None) -> list[dict]:
    from app.db import connect

    conn = connect()
    try:
        if ticket_no:
            rows = conn.execute(
                "SELECT * FROM due_date_versions WHERE ticket_no=? ORDER BY id DESC",
                (ticket_no,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM due_date_versions ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reschedule(
    ticket_no: str,
    new_due_date: str,
    reason: str,
    operator: str = "店员",
) -> dict:
    """改约：同一事务落 due_date 字段与改日流水，失败整笔回滚。

    所有前置校验都在 BEGIN IMMEDIATE 拿到写锁之后进行，消除 check-then-act 旁路；
    改约与超期隔离互斥串行，不会双判。
    """
    ticket_no = (ticket_no or "").strip()
    new_due_date = _validate_iso_date(new_due_date, "新取衣日")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(400, "改约原因必填")
    operator = (operator or "店员").strip() or "店员"
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")

    with transaction() as conn:
        # 权威日闸检查放进写事务内：结案后无法靠并发旁路改日成功。
        ensure_day_row(conn)
        gate = conn.execute(
            "SELECT sealed FROM day_gates WHERE day=?", (today_str(),)
        ).fetchone()
        if gate and gate["sealed"]:
            raise HTTPException(409, "今日已结案，禁止改约")

        row = conn.execute(
            "SELECT * FROM hang_tickets WHERE ticket_no=?", (ticket_no,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "挂牌不存在")
        if row["status"] not in RESCHEDULABLE_STATUSES:
            raise HTTPException(409, f"当前态「{row['status']}」不可改约（已取/已隔离禁改）")

        old_due_date = row["due_date"]
        if new_due_date == old_due_date:
            raise HTTPException(409, "新取衣日与现行取衣日相同，无需改约")

        # 1) 落权威字段
        conn.execute(
            "UPDATE hang_tickets SET due_date=? WHERE ticket_no=?",
            (new_due_date, ticket_no),
        )
        # 2) 写改日流水（审计，不参与判定）
        conn.execute(
            """INSERT INTO due_date_versions
               (ticket_no, old_due_date, new_due_date, reason, operator, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (ticket_no, old_due_date, new_due_date, reason, operator, now),
        )
        # 3) 同步挂工序事件，票史可追溯
        conn.execute(
            """INSERT INTO process_events(ticket_no, from_status, to_status, operator, occurred_at, note)
               VALUES (?,?,?,?,?,?)""",
            (
                ticket_no,
                row["status"],
                row["status"],
                operator,
                now,
                f"改约取衣日 {old_due_date} → {new_due_date}：{reason}",
            ),
        )

    from app.services.tickets import get_ticket

    return get_ticket(ticket_no)

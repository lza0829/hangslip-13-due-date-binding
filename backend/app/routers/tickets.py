from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services import tickets as svc
from app.services import due as due_svc

router = APIRouter(tags=["挂牌"])


class ItemIn(BaseModel):
    garment: str
    qty: int = Field(ge=1)
    remark: str = ""


class TicketIn(BaseModel):
    ticket_no: str
    store_code: str
    pickup_code: str
    customer_name: str
    due_date: str = ""
    note: str = ""
    operator: str = "店员"
    items: list[ItemIn]


class AdvanceIn(BaseModel):
    to_status: str
    operator: str = "店员"
    note: str = ""


class PickupIn(BaseModel):
    pickup_code: str
    operator: str = "店员"


class QuarantineIn(BaseModel):
    kind: str
    reason: str = ""
    operator: str = "店员"


class RescheduleIn(BaseModel):
    new_due_date: str
    reason: str = Field(min_length=1, description="改约原因必填")
    operator: str = "店员"


@router.get("/挂牌")
def list_tickets(
    status: str | None = Query(None),
    store_code: str | None = Query(None),
):
    return svc.list_tickets(status=status, store_code=store_code)


@router.get("/挂牌/{ticket_no}")
def get_ticket(ticket_no: str):
    return svc.get_ticket(ticket_no)


@router.post("/挂牌")
def create_ticket(body: TicketIn):
    return svc.create_ticket(body.model_dump())


@router.post("/挂牌/{ticket_no}/推进")
def advance(ticket_no: str, body: AdvanceIn):
    return svc.advance(ticket_no, body.to_status, body.operator, body.note)


@router.post("/挂牌/{ticket_no}/取衣")
def pickup(ticket_no: str, body: PickupIn):
    return svc.pickup(ticket_no, body.pickup_code, body.operator)


@router.post("/挂牌/{ticket_no}/隔离")
def quarantine(ticket_no: str, body: QuarantineIn):
    return svc.quarantine(ticket_no, body.kind, body.reason, body.operator)


@router.post("/挂牌/{ticket_no}/改约")
def reschedule(ticket_no: str, body: RescheduleIn):
    return due_svc.reschedule(
        ticket_no, body.new_due_date, body.reason, body.operator
    )


@router.get("/挂牌/{ticket_no}/改日流水")
def ticket_due_versions(ticket_no: str):
    return due_svc.list_due_versions(ticket_no)


@router.get("/改日流水")
def all_due_versions():
    return due_svc.list_due_versions()


@router.get("/超期扫描")
def overdue_scan():
    """超期扫描清单：只认改约后的当前取衣日，与隔离预检、总览徽章同源。"""
    from app.db import connect

    conn = connect()
    try:
        return due_svc.list_overdue(conn)
    finally:
        conn.close()

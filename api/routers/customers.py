"""
Clientes del taller.
GET /customers/        — listar (filtrar por workshop_id y/o phone)
POST /customers/       — crear cliente
GET /customers/{id}    — detalle
"""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db.database import get_connection

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    workshop_id: int
    name:        str
    phone:       Optional[str] = None
    email:       Optional[str] = None


class CustomerOut(BaseModel):
    id:          int
    workshop_id: int
    name:        str
    phone:       Optional[str]
    email:       Optional[str]
    created_at:  str


def _row_to_dict(row) -> dict:
    return {
        "id":          row["id"],
        "workshop_id": row["workshop_id"],
        "name":        row["name"],
        "phone":       row["phone"],
        "email":       row["email"],
        "created_at":  row["created_at"],
    }


@router.get("/", response_model=List[CustomerOut])
def list_customers(
    workshop_id: int = Query(...),
    phone: Optional[str] = Query(None),
):
    conn = get_connection()
    try:
        if phone:
            rows = conn.execute(
                "SELECT * FROM customers WHERE workshop_id=? AND phone=? ORDER BY id",
                (workshop_id, phone),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM customers WHERE workshop_id=? ORDER BY id",
                (workshop_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerCreate):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO customers (workshop_id, name, phone, email) VALUES (?,?,?,?)",
            (body.workshop_id, body.name, body.phone, body.email),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM customers WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Customer not found")
        return _row_to_dict(row)
    finally:
        conn.close()

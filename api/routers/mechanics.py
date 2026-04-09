from fastapi import APIRouter, HTTPException
from typing import List
from ..db.database import get_connection
from ..schemas.models import MechanicCreate, MechanicOut

router = APIRouter(prefix="/mechanics", tags=["mechanics"])


@router.get("/", response_model=List[MechanicOut])
def list_mechanics(workshop_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mechanics WHERE workshop_id = ? ORDER BY id", (workshop_id,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "workshop_id": r["workshop_id"], "name": r["name"], "active": bool(r["active"])} for r in rows]


@router.post("/", response_model=MechanicOut, status_code=201)
def create_mechanic(body: MechanicCreate):
    conn = get_connection()
    cur  = conn.execute(
        "INSERT INTO mechanics (workshop_id, name, active) VALUES (?,?,?)",
        (body.workshop_id, body.name, 1 if body.active else 0)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM mechanics WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {"id": row["id"], "workshop_id": row["workshop_id"], "name": row["name"], "active": bool(row["active"])}


@router.patch("/{mechanic_id}/toggle")
def toggle_mechanic(mechanic_id: int):
    conn = get_connection()
    row  = conn.execute("SELECT * FROM mechanics WHERE id = ?", (mechanic_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Mecánico no encontrado")
    new_active = 0 if row["active"] else 1
    conn.execute("UPDATE mechanics SET active = ? WHERE id = ?", (new_active, mechanic_id))
    conn.commit()
    conn.close()
    return {"id": mechanic_id, "active": bool(new_active)}

"""
Router /jobs — RepAIr
CRUD de trabajos + cambio de estado + delay
"""

from fastapi import APIRouter, HTTPException, Path, Query
from typing import List, Optional
from datetime import datetime

from ..db.database import get_connection
from ..schemas.models import JobCreate, JobOut, JobDelayRequest, RepairTypeCode
from ..engine.rules import get_operational_duration, DURATIONS

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _row_to_job(row) -> dict:
    d = dict(row)
    d["early_start_required"] = bool(d.get("early_start_required", 0))
    return d


# ── GET /jobs ─────────────────────────────────────────────────────────────────
@router.get("/", response_model=List[JobOut])
def list_jobs(
    workshop_id:    int,
    scheduled_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status:         Optional[str] = None,
):
    conn = get_connection()
    q    = "SELECT * FROM jobs WHERE workshop_id = ?"
    params: list = [workshop_id]
    if scheduled_date:
        q += " AND scheduled_date = ?"
        params.append(scheduled_date)
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY scheduled_date, priority"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_row_to_job(r) for r in rows]


# ── POST /jobs ────────────────────────────────────────────────────────────────
@router.post("/", response_model=JobOut, status_code=201)
def create_job(body: JobCreate):
    base   = DURATIONS[body.repair_type_code]["base"]
    buffer = DURATIONS[body.repair_type_code]["buffer"]
    now    = datetime.utcnow().isoformat()

    conn = get_connection()
    cur  = conn.execute(
        """INSERT INTO jobs
           (workshop_id, vehicle_id, customer_id, repair_type_code,
            base_duration, buffer, scheduled_date, status, priority,
            description, notes, early_start_required, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?,?,?)""",
        (
            body.workshop_id, body.vehicle_id, body.customer_id,
            body.repair_type_code, base, buffer,
            body.scheduled_date, body.priority,
            body.description, body.notes,
            1 if body.early_start_required else 0,
            now, now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _row_to_job(row)


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────
@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int = Path(...)):
    conn = get_connection()
    row  = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Trabajo no encontrado")
    return _row_to_job(row)


# ── PATCH /jobs/{id}/status ───────────────────────────────────────────────────
VALID_TRANSITIONS = {
    "pending":       {"confirmed", "cancelled", "no_show"},
    "confirmed":     {"in_progress", "cancelled", "no_show"},
    "in_progress":   {"done", "waiting_parts", "cancelled"},
    "waiting_parts": {"in_progress", "cancelled"},
    "done":          set(),
    "cancelled":     set(),
    "no_show":       set(),
    "unschedulable": {"pending"},
}

@router.patch("/{job_id}/status")
def update_status(job_id: int, new_status: str, reason: Optional[str] = None):
    conn = get_connection()
    row  = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Trabajo no encontrado")

    current = row["status"]
    if new_status not in VALID_TRANSITIONS.get(current, set()):
        conn.close()
        raise HTTPException(400, f"Transición no válida: {current} → {new_status}")

    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, job_id)
    )
    conn.execute(
        "INSERT INTO job_status_history (job_id, from_status, to_status, reason) VALUES (?,?,?,?)",
        (job_id, current, new_status, reason)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return _row_to_job(row)


# ── PATCH /jobs/{id}/delay ────────────────────────────────────────────────────
@router.patch("/{job_id}/delay")
def register_delay(job_id: int, body: JobDelayRequest):
    """
    Registra un alargue en un trabajo en curso.
    No replanifica directamente: eso lo hace POST /plan/reoptimize con trigger=intraday.
    """
    conn = get_connection()
    row  = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Trabajo no encontrado")
    if row["status"] != "in_progress":
        conn.close()
        raise HTTPException(400, "Solo se pueden registrar alargues en trabajos en_progreso")

    # Obtener el plan activo del día
    plan = conn.execute(
        """SELECT id FROM daily_plans
           WHERE workshop_id = ? AND plan_date = ?
           ORDER BY generated_at DESC LIMIT 1""",
        (row["workshop_id"], row["scheduled_date"])
    ).fetchone()

    if not plan:
        conn.close()
        raise HTTPException(404, "No hay plan activo para este día")

    conn.execute(
        "INSERT INTO job_delays (job_id, plan_id, extra_minutes, reason) VALUES (?,?,?,?)",
        (job_id, plan["id"], body.extra_minutes, body.reason)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id, "extra_minutes": body.extra_minutes}

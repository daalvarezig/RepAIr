"""
Router /plan — RepAIr
Endpoints de planificación, reoptimización y consulta de timelines
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from ..db.database import get_connection
from ..schemas.models import AcceptanceRequest, AcceptanceResponse, DailyPlanOut, PlanBlock
from ..engine.rules import JobSnapshot, acceptance_summary, DAY_CAPACITY_MIN, BOOKING_LIMIT_RATIO, MAX_COMPLEX_PER_DAY
from ..engine.planner import plan_day, timelines_to_blocks
from ..engine.reoptimizer import reoptimize_day, handle_job_delay

router = APIRouter(prefix="/plan", tags=["plan"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_jobs_for_day(conn, workshop_id: int, date: str) -> list[JobSnapshot]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE workshop_id = ? AND scheduled_date = ?",
        (workshop_id, date)
    ).fetchall()
    return [
        JobSnapshot(
            id=r["id"],
            repair_type_code=r["repair_type_code"],
            operational_duration=r["operational_duration"],
            status=r["status"],
            priority=r["priority"],
            early_start_required=bool(r["early_start_required"]),
        )
        for r in rows
    ]


def _load_mechanic_ids(conn, workshop_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM mechanics WHERE workshop_id = ? AND active = 1",
        (workshop_id,)
    ).fetchall()
    return [r["id"] for r in rows]


def _load_workshop(conn, workshop_id: int) -> dict:
    row = conn.execute("SELECT * FROM workshops WHERE id = ?", (workshop_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Taller {workshop_id} no encontrado")
    return dict(row)


def _save_plan(conn, workshop_id: int, date: str, trigger: str, blocks: list[dict], unschedulable: list[int]) -> int:
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO daily_plans (workshop_id, plan_date, generated_at, trigger) VALUES (?,?,?,?)",
        (workshop_id, date, now, trigger)
    )
    plan_id = cur.lastrowid
    for b in blocks:
        conn.execute(
            "INSERT INTO plan_blocks (plan_id, job_id, mechanic_id, start_min, end_min, score) VALUES (?,?,?,?,?,?)",
            (plan_id, b["job_id"], b["mechanic_id"], b["start_min"], b["end_min"], b.get("score"))
        )
    # Marcar no planificables
    for jid in unschedulable:
        conn.execute(
            "UPDATE jobs SET status = 'unschedulable', updated_at = ? WHERE id = ?",
            (now, jid)
        )
    conn.commit()
    return plan_id


# ── POST /plan/can-accept ─────────────────────────────────────────────────────
@router.post("/can-accept", response_model=AcceptanceResponse)
def can_accept(body: AcceptanceRequest):
    """
    Verifica si se puede aceptar un trabajo de cierto tipo para una fecha.
    No crea nada en BD.
    """
    conn = get_connection()
    ws   = _load_workshop(conn, body.workshop_id)
    jobs = _load_jobs_for_day(conn, body.workshop_id, body.scheduled_date)
    conn.close()

    result = acceptance_summary(
        repair_type_code    = body.repair_type_code,
        day_jobs            = jobs,
        total_capacity_min  = DAY_CAPACITY_MIN,
        booking_limit_ratio = ws["booking_limit_ratio"],
        max_complex         = ws["max_complex_per_day"],
    )
    return result


# ── POST /plan/day ────────────────────────────────────────────────────────────
@router.post("/day", response_model=DailyPlanOut)
def generate_plan(
    workshop_id: int,
    plan_date:   str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    trigger:     str = Query("manual"),
):
    """
    Genera y persiste el plan del día.
    Planifica todos los trabajos pending/confirmed de ese día.
    """
    conn = get_connection()
    ws           = _load_workshop(conn, workshop_id)
    jobs         = _load_jobs_for_day(conn, workshop_id, plan_date)
    mechanic_ids = _load_mechanic_ids(conn, workshop_id)

    if not mechanic_ids:
        conn.close()
        raise HTTPException(400, "No hay mecánicos activos en este taller")

    result = plan_day(
        jobs         = jobs,
        mechanic_ids = mechanic_ids,
        open_time    = ws["open_time"],
        close_time   = ws["close_time"],
        lunch_start  = ws["lunch_start"],
        lunch_end    = ws["lunch_end"],
    )
    blocks   = timelines_to_blocks(result)
    plan_id  = _save_plan(conn, workshop_id, plan_date, trigger, blocks, result.unschedulable)
    conn.close()

    return DailyPlanOut(
        plan_id       = plan_id,
        workshop_id   = workshop_id,
        plan_date     = plan_date,
        trigger       = trigger,
        blocks        = [PlanBlock(**b) for b in blocks],
        unschedulable = result.unschedulable,
    )


# ── POST /plan/reoptimize ─────────────────────────────────────────────────────
@router.post("/reoptimize", response_model=DailyPlanOut)
def reoptimize(
    workshop_id: int,
    plan_date:   str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    trigger:     str = Query("apertura"),
):
    """
    Reoptimiza el plan del día con los trabajos presentes (confirmed/pending).
    Usar trigger='apertura' a las 10:00 o trigger='intraday' durante la jornada.
    """
    conn = get_connection()
    ws           = _load_workshop(conn, workshop_id)
    jobs         = _load_jobs_for_day(conn, workshop_id, plan_date)
    mechanic_ids = _load_mechanic_ids(conn, workshop_id)

    result = reoptimize_day(
        all_jobs     = jobs,
        mechanic_ids = mechanic_ids,
        open_time    = ws["open_time"],
        close_time   = ws["close_time"],
        lunch_start  = ws["lunch_start"],
        lunch_end    = ws["lunch_end"],
    )
    blocks  = timelines_to_blocks(result)
    plan_id = _save_plan(conn, workshop_id, plan_date, trigger, blocks, result.unschedulable)
    conn.close()

    return DailyPlanOut(
        plan_id       = plan_id,
        workshop_id   = workshop_id,
        plan_date     = plan_date,
        trigger       = trigger,
        blocks        = [PlanBlock(**b) for b in blocks],
        unschedulable = result.unschedulable,
    )


# ── POST /plan/delay ──────────────────────────────────────────────────────────
@router.post("/delay")
def apply_delay(
    workshop_id:    int,
    plan_date:      str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    delayed_job_id: int = Query(...),
    extra_minutes:  int = Query(..., gt=0),
    now_min:        int = Query(..., description="Minuto actual del día (ej: 10:30 = 630)"),
    reason:         Optional[str] = None,
):
    """
    Aplica un alargue a un trabajo en curso y replanifica los afectados.
    Crea un nuevo plan con trigger='intraday'.
    """
    conn = get_connection()
    ws           = _load_workshop(conn, workshop_id)
    jobs         = _load_jobs_for_day(conn, workshop_id, plan_date)
    mechanic_ids = _load_mechanic_ids(conn, workshop_id)

    # Obtener bloques del plan activo
    active_plan = conn.execute(
        "SELECT id FROM daily_plans WHERE workshop_id=? AND plan_date=? ORDER BY generated_at DESC LIMIT 1",
        (workshop_id, plan_date)
    ).fetchone()

    if not active_plan:
        conn.close()
        raise HTTPException(404, "No hay plan activo para este día")

    current_blocks = [
        dict(b) for b in conn.execute(
            "SELECT job_id, mechanic_id, start_min, end_min, score FROM plan_blocks WHERE plan_id = ?",
            (active_plan["id"],)
        ).fetchall()
    ]

    new_blocks, unschedulable = handle_job_delay(
        delayed_job_id = delayed_job_id,
        extra_minutes  = extra_minutes,
        current_blocks = current_blocks,
        all_jobs       = jobs,
        mechanic_ids   = mechanic_ids,
        now_min        = now_min,
        open_time      = ws["open_time"],
        close_time     = ws["close_time"],
        lunch_start    = ws["lunch_start"],
        lunch_end      = ws["lunch_end"],
    )

    # Registrar delay en historial
    conn.execute(
        "INSERT INTO job_delays (job_id, plan_id, extra_minutes, reason) VALUES (?,?,?,?)",
        (delayed_job_id, active_plan["id"], extra_minutes, reason)
    )

    plan_id = _save_plan(conn, workshop_id, plan_date, "intraday", new_blocks, unschedulable)
    conn.close()

    return DailyPlanOut(
        plan_id       = plan_id,
        workshop_id   = workshop_id,
        plan_date     = plan_date,
        trigger       = "intraday",
        blocks        = [PlanBlock(**b) for b in new_blocks],
        unschedulable = unschedulable,
    )


# ── GET /plan/day ─────────────────────────────────────────────────────────────
@router.get("/day", response_model=DailyPlanOut)
def get_plan(
    workshop_id: int,
    plan_date:   str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """Devuelve el último plan generado para un día."""
    conn = get_connection()
    plan = conn.execute(
        "SELECT * FROM daily_plans WHERE workshop_id=? AND plan_date=? ORDER BY generated_at DESC LIMIT 1",
        (workshop_id, plan_date)
    ).fetchone()

    if not plan:
        conn.close()
        raise HTTPException(404, "No hay plan para este día")

    blocks_rows = conn.execute(
        "SELECT job_id, mechanic_id, start_min, end_min, score FROM plan_blocks WHERE plan_id = ?",
        (plan["id"],)
    ).fetchall()
    conn.close()

    return DailyPlanOut(
        plan_id       = plan["id"],
        workshop_id   = workshop_id,
        plan_date     = plan_date,
        trigger       = plan["trigger"],
        blocks        = [PlanBlock(**dict(b)) for b in blocks_rows],
        unschedulable = [],
    )

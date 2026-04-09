"""
Reoptimizador — RepAIr
========================
Implementa:
  - reoptimize_day()      → recalcula el plan con los trabajos presentes
  - handle_job_delay()    → gestiona un alargue y replanifica los no iniciados
"""

from __future__ import annotations
from typing import List, Dict, Tuple

from .rules import JobSnapshot
from .planner import (
    MechanicState, TimeBlock, PlanResult,
    plan_day, timelines_to_blocks,
    DEFAULT_OPEN, DEFAULT_CLOSE, DEFAULT_LUNCH_START, DEFAULT_LUNCH_END,
)


def reoptimize_day(
    all_jobs: List[JobSnapshot],
    mechanic_ids: List[int],
    open_time:    int = DEFAULT_OPEN,
    close_time:   int = DEFAULT_CLOSE,
    lunch_start:  int = DEFAULT_LUNCH_START,
    lunch_end:    int = DEFAULT_LUNCH_END,
) -> PlanResult:
    """
    Reoptimización a apertura (10:00) o intradiaria.
    Solo planifica trabajos en estado 'confirmed' o 'pending' (presentes).
    Los trabajos 'in_progress' NO se mueven.
    """
    plannable_statuses = {"pending", "confirmed"}
    plannable = [j for j in all_jobs if j.status in plannable_statuses]
    return plan_day(plannable, mechanic_ids, open_time, close_time, lunch_start, lunch_end)


def handle_job_delay(
    delayed_job_id:   int,
    extra_minutes:    int,
    current_blocks:   List[dict],       # plan_blocks del día actual (de BD)
    all_jobs:         List[JobSnapshot],
    mechanic_ids:     List[int],
    now_min:          int,              # minuto actual del día (para saber qué no ha empezado)
    open_time:        int = DEFAULT_OPEN,
    close_time:       int = DEFAULT_CLOSE,
    lunch_start:      int = DEFAULT_LUNCH_START,
    lunch_end:        int = DEFAULT_LUNCH_END,
) -> Tuple[List[dict], List[int]]:
    """
    Gestiona un alargue en un trabajo en curso.

    Pasos:
      1. Ampliar el bloque del trabajo retrasado.
      2. Detectar qué trabajos del mismo mecánico quedan bloqueados (no iniciados).
      3. Extraer esos trabajos del timeline actual.
      4. Replanificar los trabajos no iniciados bloqueados en todos los mecánicos.
      5. Retornar el nuevo conjunto de bloques + lista de no planificables.

    Retorna: (new_blocks: List[dict], unschedulable_ids: List[int])
    """
    # ── 1. Ampliar bloque del trabajo retrasado ───────────────────────────────
    updated_blocks: List[dict] = []
    delayed_mechanic_id: int = -1
    delayed_end: int = -1

    for b in current_blocks:
        if b["job_id"] == delayed_job_id:
            new_b = dict(b)
            new_b["end_min"] = b["end_min"] + extra_minutes
            updated_blocks.append(new_b)
            delayed_mechanic_id = b["mechanic_id"]
            delayed_end         = new_b["end_min"]
        else:
            updated_blocks.append(dict(b))

    if delayed_mechanic_id == -1:
        # Trabajo no encontrado en los bloques; devolver sin cambios
        return current_blocks, []

    # ── 2. Detectar trabajos bloqueados (mismo mecánico, no iniciados, después del delay) ──
    job_status_map = {j.id: j.status for j in all_jobs}
    blocked_job_ids: set[int] = set()

    for b in updated_blocks:
        if (
            b["mechanic_id"] == delayed_mechanic_id
            and b["job_id"] != delayed_job_id
            and b["start_min"] >= now_min                # no iniciado
            and job_status_map.get(b["job_id"]) not in {"in_progress", "done", "cancelled"}
        ):
            # Comprobar si ahora se solapa con el trabajo extendido
            if b["start_min"] < delayed_end:
                blocked_job_ids.add(b["job_id"])

    # ── 3. Retirar bloques bloqueados del timeline ────────────────────────────
    final_fixed_blocks = [b for b in updated_blocks if b["job_id"] not in blocked_job_ids]

    # ── 4. Replanificar los trabajos bloqueados ───────────────────────────────
    blocked_jobs = [j for j in all_jobs if j.id in blocked_job_ids]

    if not blocked_jobs:
        return final_fixed_blocks, []

    # Reconstruir el estado actual de los timelines (sin los bloqueados)
    # para que el planner sepa qué huecos ya están ocupados
    timelines: Dict[int, MechanicState] = {
        mid: MechanicState(mechanic_id=mid) for mid in mechanic_ids
    }
    for b in final_fixed_blocks:
        mid = b["mechanic_id"]
        if mid in timelines:
            timelines[mid].blocks.append(
                TimeBlock(job_id=b["job_id"], start=b["start_min"], end=b["end_min"])
            )

    # Planificar los bloqueados con preferred_start = now (no al inicio del día)
    from .planner import sort_jobs, find_first_valid_slot, score_slot

    unschedulable: List[int] = []
    sorted_blocked = sort_jobs(blocked_jobs)
    mechanics_list = list(timelines.values())

    for job in sorted_blocked:
        best_mechanic = None
        best_start    = None
        best_score    = float("-inf")

        for mechanic in mechanics_list:
            start = find_first_valid_slot(
                mechanic, job.operational_duration,
                preferred_start=now_min,
                day_end=close_time,
                lunch_start=lunch_start,
                lunch_end=lunch_end,
            )
            if start is None:
                continue
            sc = score_slot(mechanic, job, start, mechanics_list)
            if sc > best_score:
                best_score    = sc
                best_mechanic = mechanic
                best_start    = start

        if best_mechanic is not None and best_start is not None:
            sc = score_slot(best_mechanic, job, best_start, mechanics_list)
            best_mechanic.blocks.append(
                TimeBlock(job_id=job.id, start=best_start, end=best_start + job.operational_duration, score=sc)
            )
        else:
            unschedulable.append(job.id)

    # ── 5. Combinar bloques fijos + replanificados ────────────────────────────
    replanned_blocks = []
    for mid, state in timelines.items():
        for b in state.sorted_blocks():
            # Solo añadir los que son de trabajos replanificados
            if b.job_id in blocked_job_ids:
                replanned_blocks.append({
                    "job_id":      b.job_id,
                    "mechanic_id": mid,
                    "start_min":   b.start,
                    "end_min":     b.end,
                    "score":       b.score,
                })

    return final_fixed_blocks + replanned_blocks, unschedulable

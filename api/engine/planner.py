"""
Planificador diario — RepAIr
==============================
Implementa:
  - find_first_valid_slot()   → primer hueco libre respetando comida
  - score_slot()              → puntuación de un slot (inteligencia del algoritmo)
  - sort_jobs()               → orden de prioridad: complejas → standard → rápidas
  - plan_day()                → corazón del planificador
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from copy import deepcopy

from .rules import JobSnapshot, get_priority_order


# ── Configuración ─────────────────────────────────────────────────────────────

DEFAULT_OPEN       = 600   # 10:00
DEFAULT_CLOSE      = 1140  # 19:00
DEFAULT_LUNCH_START = 840  # 14:00
DEFAULT_LUNCH_END   = 900  # 15:00
COMPLEX_EARLY_MAX   = 630  # hasta 10:30 se considera "primera ola"
LATE_PENALTY_START  = 1080 # después de 18:00 penalizar


# ── Estructuras internas ──────────────────────────────────────────────────────

@dataclass
class TimeBlock:
    job_id:   int
    start:    int   # minutos desde medianoche
    end:      int
    score:    float = 0.0


@dataclass
class MechanicState:
    mechanic_id: int
    blocks: List[TimeBlock] = field(default_factory=list)

    def total_load(self) -> int:
        return sum(b.end - b.start for b in self.blocks)

    def sorted_blocks(self) -> List[TimeBlock]:
        return sorted(self.blocks, key=lambda b: b.start)


@dataclass
class PlanResult:
    timelines:     Dict[int, MechanicState]   # mechanic_id → MechanicState
    unschedulable: List[int]                  # job_ids sin hueco


# ── Utilidades de tiempo ──────────────────────────────────────────────────────

def min_to_str(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def calendar_end(
    start: int,
    working_minutes: int,
    lunch_start: int = DEFAULT_LUNCH_START,
    lunch_end:   int = DEFAULT_LUNCH_END,
) -> int:
    """
    Calcula el tiempo de calendario en que termina un trabajo de
    `working_minutes` minutos que empieza en `start`, saltando la comida.
    Ejemplo: start=600, working=300 → 600+240=840 (comida), salta a 900, +60 → 960
    """
    remaining = working_minutes
    current   = start
    if lunch_start <= current < lunch_end:
        current = lunch_end
    if current < lunch_start:
        before_lunch = lunch_start - current
        if remaining <= before_lunch:
            return current + remaining
        remaining -= before_lunch
        current    = lunch_end
    return current + remaining


def fits_in_day(
    start: int,
    working_minutes: int,
    day_end:     int = DEFAULT_CLOSE,
    lunch_start: int = DEFAULT_LUNCH_START,
    lunch_end:   int = DEFAULT_LUNCH_END,
) -> bool:
    return calendar_end(start, working_minutes, lunch_start, lunch_end) <= day_end


# ── Búsqueda de huecos ────────────────────────────────────────────────────────

def find_first_valid_slot(
    mechanic: MechanicState,
    duration: int,          # minutos de TRABAJO
    preferred_start: int = DEFAULT_OPEN,
    day_end:         int = DEFAULT_CLOSE,
    lunch_start:     int = DEFAULT_LUNCH_START,
    lunch_end:       int = DEFAULT_LUNCH_END,
) -> Optional[int]:
    """
    Devuelve el primer inicio donde caben `duration` minutos de trabajo,
    respetando bloques ocupados, comida y fin de jornada.
    """
    def try_start(s: int) -> Optional[int]:
        if lunch_start <= s < lunch_end:
            s = lunch_end
        if not fits_in_day(s, duration, day_end, lunch_start, lunch_end):
            return None
        end = calendar_end(s, duration, lunch_start, lunch_end)
        for b in mechanic.sorted_blocks():
            if s < b.end and end > b.start:
                return None
        return s

    current = max(preferred_start, DEFAULT_OPEN)
    result  = try_start(current)
    if result is not None:
        return result
    for block in mechanic.sorted_blocks():
        result = try_start(block.end)
        if result is not None:
            return result
    return None


# ── Función de score ──────────────────────────────────────────────────────────

def score_slot(
    mechanic: MechanicState,
    job: JobSnapshot,
    start: int,
    all_mechanics: List[MechanicState],
) -> float:
    """
    Cuanto mayor el score, mejor el slot.
    Reglas:
      +100  compleja arranca a primera hora (≤ 10:30)
      -80   compleja arranca tarde (> 10:30)
      +20   rápida rellena hueco pequeño
      -0.05 penalizar mecánico ya sobrecargado
      -30   trabajo termina después de las 18:00
      +10   equilibrio de carga (mecánico menos cargado)
    """
    score = 0.0
    end   = calendar_end(start, job.operational_duration)

    if job.repair_type_code == "compleja":
        if start <= COMPLEX_EARLY_MAX:
            score += 100
        else:
            score -= 80

    if job.repair_type_code == "rapida":
        score += 20

    # Penalizar mecánico sobrecargado
    load = mechanic.total_load()
    score -= load * 0.05

    # Penalizar terminar tarde
    if end > LATE_PENALTY_START:
        score -= 30

    # Premio al mecánico con menos carga (equilibrio)
    avg_load = sum(m.total_load() for m in all_mechanics) / max(len(all_mechanics), 1)
    if load < avg_load:
        score += 10

    return score


# ── Ordenación de trabajos ────────────────────────────────────────────────────

def sort_jobs(jobs: List[JobSnapshot]) -> List[JobSnapshot]:
    """
    Orden de planificación:
      1. complejas (priority_order=1)
      2. standard  (priority_order=2)
      3. rápidas   (priority_order=3)
    Dentro de cada grupo: por prioridad explícita, luego por duración desc.
    """
    return sorted(
        jobs,
        key=lambda j: (
            get_priority_order(j.repair_type_code),
            j.priority,
            -j.operational_duration,
        ),
    )


# ── Planificador principal ────────────────────────────────────────────────────

def plan_day(
    jobs:      List[JobSnapshot],
    mechanic_ids: List[int],
    open_time:    int = DEFAULT_OPEN,
    close_time:   int = DEFAULT_CLOSE,
    lunch_start:  int = DEFAULT_LUNCH_START,
    lunch_end:    int = DEFAULT_LUNCH_END,
) -> PlanResult:
    """
    Genera el plan del día.
    - Ordena trabajos: complejas → standard → rápidas
    - Para complejas intenta asignar al inicio de jornada (first slot == open_time)
    - Para el resto busca el mejor slot por score
    - Retorna timelines por mecánico y lista de no planificables
    """
    timelines: Dict[int, MechanicState] = {
        mid: MechanicState(mechanic_id=mid) for mid in mechanic_ids
    }
    unschedulable: List[int] = []
    sorted_jobs = sort_jobs([j for j in jobs if j.status in {"pending", "confirmed"}])

    for job in sorted_jobs:
        mechanics_list = list(timelines.values())
        assigned = False

        # ── Complejas: intentar primera hora primero ──────────────────────────
        if job.repair_type_code == "compleja":
            for mechanic in mechanics_list:
                start = find_first_valid_slot(
                    mechanic, job.operational_duration,
                    preferred_start=open_time,
                    day_end=close_time,
                    lunch_start=lunch_start,
                    lunch_end=lunch_end,
                )
                # Aceptar si arranca en la primera ola (hasta 10:30)
                if start is not None and start <= COMPLEX_EARLY_MAX:
                    sc = score_slot(mechanic, job, start, mechanics_list)
                    end_cal = calendar_end(start, job.operational_duration)
                    mechanic.blocks.append(TimeBlock(job_id=job.id, start=start, end=end_cal, score=sc))
                    assigned = True
                    break

        # ── Fallback: mejor score entre todos los mecánicos ───────────────────
        if not assigned:
            best_mechanic: Optional[MechanicState] = None
            best_start:    Optional[int] = None
            best_score:    float = float("-inf")

            for mechanic in mechanics_list:
                start = find_first_valid_slot(
                    mechanic, job.operational_duration,
                    preferred_start=open_time,
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
                sc      = score_slot(best_mechanic, job, best_start, mechanics_list)
                end_cal = calendar_end(best_start, job.operational_duration)
                best_mechanic.blocks.append(
                    TimeBlock(job_id=job.id, start=best_start, end=end_cal, score=sc)
                )
                assigned = True

        if not assigned:
            unschedulable.append(job.id)

    return PlanResult(timelines=timelines, unschedulable=unschedulable)


def timelines_to_blocks(result: PlanResult) -> List[dict]:
    """Convierte PlanResult a lista de dicts para persistir en plan_blocks."""
    blocks = []
    for mid, state in result.timelines.items():
        for b in state.sorted_blocks():
            blocks.append({
                "job_id":      b.job_id,
                "mechanic_id": mid,
                "start_min":   b.start,
                "end_min":     b.end,
                "score":       b.score,
            })
    return blocks

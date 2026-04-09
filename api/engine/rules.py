"""
Motor de reglas de negocio — RepAIr
====================================
Reglas de aceptación y duraciones operativas.
No depende de BD: recibe los datos ya cargados.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple


# ── Constantes por defecto ────────────────────────────────────────────────────

DURATIONS: dict[str, dict] = {
    "rapida":   {"base": 45,  "buffer": 15, "priority": 3},
    "standard": {"base": 90,  "buffer": 30, "priority": 2},
    "compleja": {"base": 240, "buffer": 60, "priority": 1},
}

DAY_CAPACITY_MIN       = 1440   # 3 mecánicos × 8h = 1440 min
BOOKING_LIMIT_RATIO    = 0.85
MAX_COMPLEX_PER_DAY    = 2
COMPLEX_REQUIRED_BLOCK = 300    # 240 base + 60 buffer


# ── Tipos auxiliares ──────────────────────────────────────────────────────────

@dataclass
class JobSnapshot:
    """Representación mínima de un trabajo para las reglas."""
    id:                   int
    repair_type_code:     str
    operational_duration: int   # base + buffer
    status:               str
    priority:             int
    early_start_required: bool = False


# ── Duraciones ────────────────────────────────────────────────────────────────

def get_operational_duration(repair_type_code: str) -> int:
    """Devuelve la duración operativa (base + buffer) en minutos."""
    t = DURATIONS.get(repair_type_code)
    if not t:
        raise ValueError(f"Tipo de reparación desconocido: {repair_type_code}")
    return t["base"] + t["buffer"]


def get_priority_order(repair_type_code: str) -> int:
    return DURATIONS.get(repair_type_code, {}).get("priority", 99)


# ── Reglas de aceptación ──────────────────────────────────────────────────────

def count_complex_jobs(day_jobs: List[JobSnapshot]) -> int:
    active_statuses = {"pending", "confirmed", "in_progress", "waiting_parts"}
    return sum(
        1 for j in day_jobs
        if j.repair_type_code == "compleja" and j.status in active_statuses
    )


def reserved_minutes(day_jobs: List[JobSnapshot]) -> int:
    active_statuses = {"pending", "confirmed", "in_progress", "waiting_parts"}
    return sum(j.operational_duration for j in day_jobs if j.status in active_statuses)


def can_accept_job(
    repair_type_code: str,
    day_jobs: List[JobSnapshot],
    total_capacity_min: int = DAY_CAPACITY_MIN,
    booking_limit_ratio: float = BOOKING_LIMIT_RATIO,
    max_complex: int = MAX_COMPLEX_PER_DAY,
) -> Tuple[bool, str]:
    """
    Regla principal de aceptación.
    Devuelve (accepted: bool, reason: str).
    """
    op_duration = get_operational_duration(repair_type_code)
    used = reserved_minutes(day_jobs)
    limit = total_capacity_min * booking_limit_ratio

    # ── Regla 1: capacidad global ─────────────────────────────────────────────
    if used + op_duration > limit:
        remaining = max(0, int(limit - used))
        return False, (
            f"Capacidad diaria superada. "
            f"Disponible: {remaining} min, necesario: {op_duration} min."
        )

    # ── Regla 2: límite de complejas ─────────────────────────────────────────
    if repair_type_code == "compleja":
        complex_count = count_complex_jobs(day_jobs)
        if complex_count >= max_complex:
            return False, f"Ya hay {complex_count} reparaciones complejas ese día (máximo {max_complex})."

        # ── Regla 3: bloque operativo de 5h para complejas ────────────────────
        # Necesitamos que exista al menos un mecánico con 300 min libres
        # (esto se valida con más precisión en el planner; aquí verificamos
        #  si globalmente queda margen suficiente)
        if used + COMPLEX_REQUIRED_BLOCK > limit:
            return False, (
                f"No queda bloque operativo suficiente para una compleja "
                f"({COMPLEX_REQUIRED_BLOCK} min requeridos)."
            )

    return True, "Trabajo aceptable."


def acceptance_summary(
    repair_type_code: str,
    day_jobs: List[JobSnapshot],
    total_capacity_min: int = DAY_CAPACITY_MIN,
    booking_limit_ratio: float = BOOKING_LIMIT_RATIO,
    max_complex: int = MAX_COMPLEX_PER_DAY,
) -> dict:
    """Devuelve dict completo para el endpoint /can-accept."""
    accepted, reason = can_accept_job(
        repair_type_code, day_jobs, total_capacity_min, booking_limit_ratio, max_complex
    )
    used  = reserved_minutes(day_jobs)
    limit = total_capacity_min * booking_limit_ratio
    return {
        "accepted":                accepted,
        "reason":                  reason,
        "remaining_capacity_min":  max(0, int(limit - used)),
        "complex_count":           count_complex_jobs(day_jobs),
        "max_complex":             max_complex,
    }

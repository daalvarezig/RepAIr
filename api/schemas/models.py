from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class RepairTypeCode(str, Enum):
    rapida   = "rapida"
    standard = "standard"
    compleja = "compleja"


class JobStatus(str, Enum):
    pending       = "pending"
    confirmed     = "confirmed"
    in_progress   = "in_progress"
    waiting_parts = "waiting_parts"
    done          = "done"
    cancelled     = "cancelled"
    no_show       = "no_show"
    unschedulable = "unschedulable"


class PlanTrigger(str, Enum):
    manual   = "manual"
    apertura = "apertura"
    intraday = "intraday"
    auto     = "auto"


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    workshop_id:        int
    vehicle_id:         Optional[int] = None
    customer_id:        Optional[int] = None
    repair_type_code:   RepairTypeCode
    scheduled_date:     str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    priority:           int = Field(5, ge=1, le=10)
    description:        Optional[str] = None
    notes:              Optional[str] = None
    early_start_required: bool = False


class JobOut(BaseModel):
    id:                  int
    workshop_id:         int
    vehicle_id:          Optional[int]
    customer_id:         Optional[int]
    repair_type_code:    str
    base_duration:       int
    buffer:              int
    operational_duration: int
    scheduled_date:      str
    status:              str
    priority:            int
    description:         Optional[str]
    notes:               Optional[str]
    early_start_required: bool
    created_at:          str
    updated_at:          str


class JobDelayRequest(BaseModel):
    extra_minutes: int = Field(..., gt=0)
    reason:        Optional[str] = None


# ── Plan ──────────────────────────────────────────────────────────────────────

class PlanBlock(BaseModel):
    job_id:      int
    mechanic_id: int
    start_min:   int   # minutos desde medianoche
    end_min:     int
    score:       Optional[float] = None

    @property
    def start_time(self) -> str:
        h, m = divmod(self.start_min, 60)
        return f"{h:02d}:{m:02d}"

    @property
    def end_time(self) -> str:
        h, m = divmod(self.end_min, 60)
        return f"{h:02d}:{m:02d}"


class DailyPlanOut(BaseModel):
    plan_id:      int
    workshop_id:  int
    plan_date:    str
    trigger:      str
    blocks:       List[PlanBlock]
    unschedulable: List[int]  # job_ids que no cupen


class MechanicTimeline(BaseModel):
    mechanic_id:   int
    mechanic_name: str
    blocks:        List[PlanBlock]
    total_load_min: int
    free_min:      int


# ── Acceptance check ──────────────────────────────────────────────────────────

class AcceptanceRequest(BaseModel):
    workshop_id:      int
    repair_type_code: RepairTypeCode
    scheduled_date:   str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class AcceptanceResponse(BaseModel):
    accepted:  bool
    reason:    str
    remaining_capacity_min: int
    complex_count:   int
    max_complex:     int


# ── Mechanics ─────────────────────────────────────────────────────────────────

class MechanicCreate(BaseModel):
    workshop_id: int
    name:        str
    active:      bool = True


class MechanicOut(BaseModel):
    id:          int
    workshop_id: int
    name:        str
    active:      bool


# ── Workshop ──────────────────────────────────────────────────────────────────

class WorkshopOut(BaseModel):
    id:                    int
    name:                  str
    open_time:             int
    close_time:            int
    lunch_start:           int
    lunch_end:             int
    max_complex_per_day:   int
    booking_limit_ratio:   float

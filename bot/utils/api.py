"""
Cliente HTTP para la API RepAIr.
Todas las llamadas al backend pasan por aquí.
"""
from __future__ import annotations
import os
import httpx
from datetime import date, timedelta
from typing import Optional

API_BASE    = os.getenv("API_BASE", "http://127.0.0.1:8010")
WORKSHOP_ID = int(os.getenv("WORKSHOP_ID", "1"))

TIPO_LABELS = {
    "rapida":   "⚡ Rápida (~45 min)",
    "standard": "🔧 Standard (~90 min)",
    "compleja": "🔩 Compleja (~4h)",
}
TIPO_CODES = list(TIPO_LABELS.keys())


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=10)


# ── Disponibilidad ────────────────────────────────────────────────────────────

def get_availability(target_date: str) -> dict:
    """
    Devuelve qué tipos de trabajo caben en una fecha.
    {
      "date": "2026-04-10",
      "rapida": True,
      "standard": True,
      "compleja": False,
      "complex_count": 2,
      "remaining_min": 300
    }
    """
    result = {"date": target_date, "remaining_min": 0, "complex_count": 0}
    with _client() as c:
        for tipo in TIPO_CODES:
            try:
                r = c.post("/plan/can-accept", json={
                    "workshop_id":      WORKSHOP_ID,
                    "repair_type_code": tipo,
                    "scheduled_date":   target_date,
                })
                data = r.json()
                result[tipo]             = data.get("accepted", False)
                result["remaining_min"]  = data.get("remaining_capacity_min", 0)
                result["complex_count"]  = data.get("complex_count", 0)
            except Exception:
                result[tipo] = False
    return result


def get_week_availability() -> list[dict]:
    """Disponibilidad de los próximos 7 días laborables."""
    results = []
    d = date.today()
    checked = 0
    while checked < 7:
        if d.weekday() < 6:  # lunes–sábado
            results.append(get_availability(d.isoformat()))
            checked += 1
        d += timedelta(days=1)
    return results


# ── Crear reserva ─────────────────────────────────────────────────────────────

def create_booking(
    scheduled_date:   str,
    repair_type_code: str,
    customer_name:    str,
    customer_phone:   str,
    description:      Optional[str] = None,
) -> dict:
    """Crea cliente (si no existe) y job. Devuelve el job creado."""
    with _client() as c:
        # Crear o reutilizar cliente por teléfono
        customer_id = _get_or_create_customer(c, customer_name, customer_phone)
        r = c.post("/jobs/", json={
            "workshop_id":      WORKSHOP_ID,
            "customer_id":      customer_id,
            "repair_type_code": repair_type_code,
            "scheduled_date":   scheduled_date,
            "priority":         5,
            "description":      description or "",
        })
        r.raise_for_status()
        return r.json()


def _get_or_create_customer(c: httpx.Client, name: str, phone: str) -> int:
    """Busca cliente por teléfono o lo crea. Devuelve customer_id."""
    try:
        r = c.get("/customers/", params={"workshop_id": WORKSHOP_ID, "phone": phone})
        if r.status_code == 200:
            data = r.json()
            if data:
                return data[0]["id"]
    except Exception:
        pass
    # Crear nuevo
    r = c.post("/customers/", json={
        "workshop_id": WORKSHOP_ID,
        "name":        name,
        "phone":       phone,
    })
    if r.status_code in (200, 201):
        return r.json()["id"]
    return None


# ── Plan del día ──────────────────────────────────────────────────────────────

def get_job(job_id: int) -> dict:
    with _client() as c:
        r = c.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return r.json()


def get_day_plan(plan_date: str) -> dict | None:
    with _client() as c:
        r = c.get("/plan/day", params={"workshop_id": WORKSHOP_ID, "plan_date": plan_date})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def get_mechanics() -> list[dict]:
    with _client() as c:
        r = c.get("/mechanics/", params={"workshop_id": WORKSHOP_ID})
        r.raise_for_status()
        return r.json()


def get_jobs_for_day(plan_date: str) -> list[dict]:
    with _client() as c:
        r = c.get("/jobs/", params={"workshop_id": WORKSHOP_ID, "scheduled_date": plan_date})
        r.raise_for_status()
        return r.json()


def reoptimize(plan_date: str, trigger: str = "apertura") -> dict:
    with _client() as c:
        r = c.post("/plan/reoptimize", params={
            "workshop_id": WORKSHOP_ID,
            "plan_date":   plan_date,
            "trigger":     trigger,
        })
        r.raise_for_status()
        return r.json()


# ── Helpers de formato ────────────────────────────────────────────────────────

def fmt_min(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def fmt_availability_line(av: dict) -> str:
    d     = date.fromisoformat(av["date"])
    day   = d.strftime("%a %d/%m").capitalize()
    tipos = []
    if av.get("compleja"): tipos.append("🔩")
    if av.get("standard"): tipos.append("🔧")
    if av.get("rapida"):   tipos.append("⚡")
    if not tipos:
        return f"  {day} — 🔴 Completo"
    return f"  {day} — {''.join(tipos)} libre"

# RepAIr — Progreso de desarrollo

> Planificador de capacidad inteligente para taller de motos

---

## Estado general: 🟢 FASE 1 COMPLETADA

**Última actualización:** 2026-04-09

---

## Fases

| Fase | Descripción | Estado |
|------|-------------|--------|
| 0 | Infraestructura y modelo SQL | ✅ Completo |
| 1 | Motor de reglas (FastAPI) | ✅ Completo |
| 2 | Vista diaria por mecánico (frontend) | ⬜ Pendiente |
| 3 | Bot Telegram reservas | ⬜ Pendiente |
| 4 | V2 features (esperas, piezas, WhatsApp) | ⬜ Pendiente |
| 5 | V3 / SaaS / KPIs | ⬜ Pendiente |

---

## Decisiones tomadas

| Decisión | Valor |
|----------|-------|
| Stack backend | Python 3.12 + FastAPI + SQLite |
| Ubicación | `/opt/itopy.ai/apps/RepAIr/` |
| DB path | `/opt/itopy.ai/data/repair/repair.db` |
| Puerto API | 8010 |
| Subdominio | repair.itopy.ai (pendiente nginx) |
| Duración rápida | 60 min (45 base + 15 buffer) |
| Duración standard | 120 min (90 base + 30 buffer) |
| Duración compleja | 300 min (240 base + 60 buffer) — CRUZA COMIDA |
| Capacidad diaria | 3 mecánicos × 8h = 1440 min, reservable 85% = 1224 min |
| Horario | 10:00–14:00 y 15:00–19:00 |
| Máx. complejas/día | 2 |

### Decisión técnica importante: calendar_end vs duration
Una compleja de 300 min empieza a las 10:00 y termina a las **16:00** (no 15:00).
El sistema trabaja en "minutos de trabajo" y convierte a tiempo de calendario
sumando la pausa de comida si el trabajo la atraviesa.
- `calendar_end(600, 300)` → 960 (16:00) ✓

---

## Estructura del proyecto

```
/opt/itopy.ai/apps/RepAIr/
├── PROGRESS.md
└── api/
    ├── main.py                  ← FastAPI app, startup, CORS
    ├── requirements.txt         ← fastapi, uvicorn, pydantic, python-dotenv
    ├── .env                     ← DATABASE_PATH, PORT
    ├── .env.example
    ├── repair.service           ← systemd unit (instalar manualmente)
    ├── db/
    │   ├── database.py          ← get_connection(), init_db()
    │   └── schema.sql           ← DDL completo con datos iniciales
    ├── engine/
    │   ├── rules.py             ← can_accept_job, acceptance_summary, JobSnapshot
    │   ├── planner.py           ← plan_day, find_first_valid_slot, score_slot, calendar_end
    │   └── reoptimizer.py       ← reoptimize_day, handle_job_delay
    ├── routers/
    │   ├── jobs.py              ← CRUD jobs + status transitions + delay
    │   ├── plan.py              ← can-accept, plan/day, reoptimize, delay, GET day
    │   └── mechanics.py         ← CRUD mecánicos
    └── schemas/
        └── models.py            ← Pydantic schemas (JobCreate, JobOut, PlanBlock, etc.)
```

---

## Endpoints disponibles (Puerto 8010)

### Jobs
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/jobs/?workshop_id=1&scheduled_date=YYYY-MM-DD` | Listar trabajos del día |
| POST | `/jobs/` | Crear trabajo |
| GET | `/jobs/{id}` | Obtener trabajo |
| PATCH | `/jobs/{id}/status?new_status=confirmed` | Cambiar estado |
| PATCH | `/jobs/{id}/delay` | Registrar alargue |

### Plan
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/plan/can-accept` | ¿Cabe este trabajo en este día? |
| POST | `/plan/day?workshop_id=1&plan_date=YYYY-MM-DD` | Generar plan del día |
| POST | `/plan/reoptimize?workshop_id=1&plan_date=YYYY-MM-DD&trigger=apertura` | Reoptimizar (apertura o intraday) |
| POST | `/plan/delay?workshop_id=1&plan_date=...&delayed_job_id=1&extra_minutes=30&now_min=700` | Aplicar delay + replanificar |
| GET | `/plan/day?workshop_id=1&plan_date=YYYY-MM-DD` | Ver plan activo del día |

### Mechanics
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/mechanics/?workshop_id=1` | Listar mecánicos |
| POST | `/mechanics/` | Crear mecánico |
| PATCH | `/mechanics/{id}/toggle` | Activar/desactivar mecánico |

---

## Tablas SQL

| Tabla | Descripción |
|-------|-------------|
| `workshops` | Config del taller (horario, ratios, máx complejas) |
| `mechanics` | Mecánicos (activo/inactivo) |
| `repair_types` | Tipos con duración configurable por taller |
| `customers` | Clientes |
| `vehicles` | Vehículos (principalmente motos) |
| `jobs` | Trabajos/reservas con ciclo de vida completo |
| `daily_plans` | Snapshot de cada planificación |
| `plan_blocks` | Asignación job→mecánico→hora |
| `job_status_history` | Auditoría de cambios de estado |
| `job_delays` | Historial de alargues intradiarios |

### Ciclo de vida de un job
```
pending → confirmed → in_progress → done
                    ↘ waiting_parts → in_progress
         ↘ cancelled
         ↘ no_show
unschedulable → pending (revisión manual)
```

---

## Algoritmo — resumen

### Orden de planificación
1. Complejas (empiezan a las 10:00, primera ola)
2. Standard (distribuidas por score)
3. Rápidas (rellenan huecos)

### Score de asignación
- `+100` compleja arranca ≤ 10:30
- `-80`  compleja arranca > 10:30
- `+20`  rápida rellena hueco
- `-0.05 × carga_mecanico` penalizar sobrecarga
- `-30`  trabajo termina > 18:00
- `+10`  mecánico menos cargado (equilibrio)

### Reoptimización
- **Apertura (10:00):** solo planifica `confirmed`/`pending` presentes
- **Intraday:** extiende el bloque afectado, saca los no-iniciados bloqueados, replanifica

---

## Log de avance

### 2026-04-09 — Fase 1 completada
- [x] Exploración de infraestructura
- [x] Nombre: RepAIr, subdominio: repair.itopy.ai
- [x] Modelo SQL (10 tablas, constraints, datos iniciales)
- [x] Motor de reglas (`rules.py`)
- [x] Planificador con `calendar_end` para cruzar comida correctamente
- [x] Reoptimizador (apertura + intraday delay)
- [x] Todos los endpoints FastAPI
- [x] API testeada: health ✓, can-accept ✓, crear jobs ✓, plan/day ✓
- [x] systemd unit generado (`repair.service`)
- [x] Bug fix: `overlaps_lunch` → `calendar_end` (compleja 10:00–16:00, no 15:00)
- [x] Bug fix: INSERT jobs 13→14 values

---

## Próximos pasos (Fase 2)

### Para continuar aquí
1. **Instalar servicio** (requiere sudo):
   ```bash
   sudo cp /opt/itopy.ai/apps/RepAIr/api/repair.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now repair
   ```

2. **Nginx** para repair.itopy.ai → proxy_pass http://127.0.0.1:8010

3. **Fase 2: Vista diaria** — React/HTML en `/opt/itopy.ai/apps/RepAIr/frontend/`
   - Timeline tipo Gantt por mecánico
   - Botón "Reoptimizar día"
   - Indicadores: % ocupación, complejas, huecos muertos

4. **Fase 3: Bot Telegram** — `/reservar`, `/disponibilidad YYYY-MM-DD`

---

## Arrancar la API (sin systemd)
```bash
cd /opt/itopy.ai/apps/RepAIr
DATABASE_PATH=/opt/itopy.ai/data/repair/repair.db \
  /home/david/itopyzone/venv/bin/uvicorn api.main:app \
  --host 127.0.0.1 --port 8010
```

Documentación interactiva: http://127.0.0.1:8010/docs

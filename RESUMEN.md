# RepAIr — Resumen del proyecto

> Sistema de gestión inteligente para talleres de motos.  
> Reservas automáticas · Planificación por IA · Dashboard en tiempo real.

---

## Estado actual

| Componente | Estado |
|---|---|
| API REST (FastAPI) | ✅ Producción |
| Motor de planificación IA | ✅ Producción |
| Bot de reservas (Telegram) | ✅ Producción |
| Dashboard cyberpunk | ✅ Producción — `repair.itopy.ai` |
| Landing de presentación | ✅ `repair.itopy.ai/demo.html` |

---

## Arquitectura

```
Cliente (Telegram/WhatsApp/...)
        ↓
    Bot de reservas
        ↓
    API FastAPI  ←→  SQLite DB
        ↓
  Motor de planificación IA
        ↓
  Dashboard (nginx → HTML estático)
```

**Servicios systemd:**
- `repair` — API FastAPI en `http://127.0.0.1:8010`
- `repair_bot` — Bot de Telegram

**Rutas clave:**
- API: `/opt/itopy.ai/apps/RepAIr/api/`
- Bot: `/opt/itopy.ai/apps/RepAIr/bot/`
- Frontend: `/opt/itopy.ai/apps/RepAIr/frontend/`
- Base de datos: `/opt/itopy.ai/data/repair/repair.db`

---

## Funcionalidades implementadas

### API (`/api/`)

- `POST /jobs/` — Crear cita. Acepta `status` opcional (default `pending`)
- `GET /jobs/` — Listar citas con filtros por fecha, workshop, status
- `GET /jobs/{id}` — Detalle de cita
- `PATCH /jobs/{id}/status` — Cambiar estado + `notes` opcional
- `POST /plan/` — Generar plan optimizado para un día
- `GET /plan/{date}` — Obtener plan del día
- `GET /acceptance/` — Comprobar si el taller acepta un tipo/fecha
- `GET /customers/` — Listar/buscar clientes por teléfono
- `POST /customers/` — Crear cliente
- `GET /mechanics/` — Listar mecánicos
- `GET /health` — Health check

### Motor de planificación

- Asignación óptima de citas a mecánicos
- Respeta capacidad máxima del taller
- Límite de reparaciones complejas por día
- Bloque de comida automático
- Reoptimización on-demand (botón en dashboard)
- Trigger: manual / apertura / intraday / auto

### Bot de reservas

- `/reservar` — Flujo completo: fecha → tipo → nombre → teléfono → confirmar
  - Crea la cita directamente como `confirmed`
  - Notificación inmediata al owner
- `/cancelar_cita` — Busca citas por teléfono y cancela la elegida
- `/estado` — Ver estado de una cita por ID
- `/start` — Bienvenida

### Dashboard (`repair.itopy.ai`)

- KPIs: citas totales, confirmadas, complejas, capacidad libre, no planificables
- Gantt timeline por mecánico (colores por tipo: rápida/standard/compleja)
- Tabla de citas del día (sin canceladas)
- Selector de fecha
- Botón REOPTIMIZAR
- Auto-refresco cada 60 segundos

> **Nota frontend:** El frontend es HTML estático puro (sin framework, sin build) servido por nginx.
> Ficheros: `index.html` (dashboard), `demo.html`, `mockup.html`.
> **No es PWA** — no tiene manifest ni service worker. Es un draft funcional para demos con clientes.

---

## Estados de una cita (`JobStatus`)

| Estado | Significado | Transiciones permitidas |
|---|---|---|
| `pending` | En espera / owner pendiente de confirmar | → confirmed, cancelled, no_show |
| `confirmed` | Confirmada | → in_progress, cancelled, no_show, **pending** |
| `in_progress` | En curso | → done, waiting_parts, cancelled |
| `waiting_parts` | Esperando pieza | → in_progress, cancelled |
| `done` | Finalizada | — |
| `cancelled` | Cancelada | — |
| `no_show` | Cliente no apareció | — |
| `unschedulable` | No cabe en el día | → pending |

**Regla de oro:**
- Reservas del bot → siempre `confirmed` (el cliente confirmó activamente)
- `pending` es para el owner cuando hay algo pendiente de resolver (pieza, confirmación, etc.)
- `pending` requiere nota explicativa cuando se baja de `confirmed`

---

## Modelo de datos — Jobs

```
id, workshop_id, vehicle_id, customer_id
repair_type_code: rapida | standard | compleja
base_duration, buffer, operational_duration
scheduled_date (YYYY-MM-DD)
status
priority (1-10)
description
notes          ← campo libre para el owner
early_start_required
created_at, updated_at
```

---

## Tipos de reparación

| Código | Duración base | Buffer | Total |
|---|---|---|---|
| `rapida` | 45 min | 15 min | 60 min |
| `standard` | 90 min | 30 min | 120 min |
| `compleja` | 240 min | 60 min | 300 min |

---

## Fase 4 — Pendiente

- [ ] `waiting_parts` — flujo owner para marcar cita en espera de pieza
- [ ] Notificaciones intraday — avisos automáticos al cliente (recordatorio, lista)
- [ ] WhatsApp Business / Instagram DMs — mismo motor, distinto canal
- [ ] Chat interno — para que el owner introduzca reservas telefónicas desde el dashboard
- [ ] Cambio de estado desde el dashboard (sin tocar la API a mano)
- [ ] Campo `notes` visible en el dashboard + editable por el owner

---

## Comandos útiles

```bash
# Reiniciar servicios
sudo systemctl restart repair repair_bot

# Ver logs
journalctl -u repair -f
journalctl -u repair_bot -f

# Health check API
curl http://127.0.0.1:8010/health

# Acceso directo a BD
sqlite3 /opt/itopy.ai/data/repair/repair.db

# Ver citas de hoy
sqlite3 /opt/itopy.ai/data/repair/repair.db \
  "SELECT id, status, repair_type_code, description FROM jobs WHERE scheduled_date=date('now')"
```

---

## URLs

| Recurso | URL |
|---|---|
| Dashboard | https://repair.itopy.ai |
| Demo / presentación | https://repair.itopy.ai/demo.html |
| API docs (Swagger) | http://127.0.0.1:8010/docs |

---

*Última actualización: 2026-04-12*

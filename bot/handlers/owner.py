"""
Comandos exclusivos del owner del taller.
/plan, /reoptimizar, /citas
"""
from __future__ import annotations
import os
from datetime import date
from telegram import Update
from telegram.ext import ContextTypes

from utils.api import (
    get_day_plan, get_mechanics, get_jobs_for_day,
    reoptimize, fmt_min, TIPO_LABELS,
)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

STATUS_EMOJI = {
    "pending":       "⏳",
    "confirmed":     "✅",
    "in_progress":   "🔄",
    "waiting_parts": "⏸️",
    "done":          "✔️",
    "cancelled":     "❌",
    "no_show":       "👻",
    "unschedulable": "⚠️",
}


def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


def _parse_date(args: list[str]) -> str:
    if args:
        try:
            date.fromisoformat(args[0])
            return args[0]
        except ValueError:
            pass
    return date.today().isoformat()


# ── /plan ─────────────────────────────────────────────────────────────────────

async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await update.message.reply_text("❌ Solo el owner puede ver el plan.")
        return

    plan_date = _parse_date(ctx.args)
    await update.message.reply_text(f"⏳ Cargando plan del {plan_date}...")

    plan = get_day_plan(plan_date)
    if not plan:
        await update.message.reply_text(
            f"📋 No hay plan generado para {plan_date}.\n"
            f"Usa /reoptimizar {plan_date} para generarlo."
        )
        return

    mechanics = {m["id"]: m["name"] for m in get_mechanics()}
    blocks    = plan.get("blocks", [])

    if not blocks:
        await update.message.reply_text(f"📋 Plan del {plan_date}: sin trabajos planificados.")
        return

    # Agrupar por mecánico
    by_mec: dict[int, list] = {}
    for b in sorted(blocks, key=lambda x: (x["mechanic_id"], x["start_min"])):
        by_mec.setdefault(b["mechanic_id"], []).append(b)

    lines = [f"📋 *Plan {plan_date}*\n"]
    for mid, mblocks in by_mec.items():
        name  = mechanics.get(mid, f"Mec {mid}")
        total = sum(b["end_min"] - b["start_min"] for b in mblocks)
        lines.append(f"👨‍🔧 *{name}* ({total//60}h{total%60:02d}m)")
        for b in mblocks:
            lines.append(
                f"  {fmt_min(b['start_min'])}–{fmt_min(b['end_min'])} "
                f"· job #{b['job_id']}"
            )
        lines.append("")

    unsch = plan.get("unschedulable", [])
    if unsch:
        lines.append(f"⚠️ Sin planificar: jobs {unsch}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /reoptimizar ──────────────────────────────────────────────────────────────

async def cmd_reoptimizar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await update.message.reply_text("❌ Solo el owner puede reoptimizar.")
        return

    plan_date = _parse_date(ctx.args)
    trigger   = "apertura" if plan_date == date.today().isoformat() else "manual"
    await update.message.reply_text(f"⚙️ Reoptimizando {plan_date}...")

    try:
        result = reoptimize(plan_date, trigger)
        blocks = result.get("blocks", [])
        unsch  = result.get("unschedulable", [])
        msg    = (
            f"✅ Plan regenerado para {plan_date}\n"
            f"  Bloques: {len(blocks)}\n"
            f"  No planificables: {len(unsch)}"
        )
        if unsch:
            msg += f" (jobs {unsch})"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── /citas ────────────────────────────────────────────────────────────────────

async def cmd_citas(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await update.message.reply_text("❌ Solo el owner puede ver las citas.")
        return

    plan_date = _parse_date(ctx.args)
    await update.message.reply_text(f"⏳ Cargando citas del {plan_date}...")

    try:
        jobs = get_jobs_for_day(plan_date)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if not jobs:
        await update.message.reply_text(f"📅 Sin citas para {plan_date}.")
        return

    lines = [f"📅 *Citas {plan_date}* ({len(jobs)} trabajos)\n"]
    for j in jobs:
        emoji = STATUS_EMOJI.get(j["status"], "•")
        tipo  = TIPO_LABELS.get(j["repair_type_code"], j["repair_type_code"])
        desc  = j.get("description") or ""
        lines.append(
            f"{emoji} #{j['id']} · {tipo}\n"
            f"   {j['status']}"
            + (f" · {desc[:40]}" if desc else "")
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

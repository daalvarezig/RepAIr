"""
Comandos para clientes (y owner).
/disponibilidad, /reservar (ConversationHandler), /estado
"""
from __future__ import annotations
import os
from datetime import date
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, MessageHandler, filters,
)

from utils.api import (
    get_week_availability, get_availability,
    create_booking, get_job, fmt_availability_line, TIPO_LABELS,
)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Estados de la conversación /reservar
ASK_DATE, ASK_TIPO, ASK_NAME, ASK_PHONE, CONFIRM = range(5)


# ── /disponibilidad ───────────────────────────────────────────────────────────

async def cmd_disponibilidad(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # Con argumento: /disponibilidad 2026-04-15
    if ctx.args:
        try:
            date.fromisoformat(ctx.args[0])
            av   = get_availability(ctx.args[0])
            d    = date.fromisoformat(av["date"])
            day  = d.strftime("%A %d/%m").capitalize()
            tipos = []
            for code, label in TIPO_LABELS.items():
                estado = "✅ Disponible" if av.get(code) else "🔴 Completo"
                tipos.append(f"  {label}: {estado}")
            msg = (
                f"📅 *{day}*\n\n"
                + "\n".join(tipos)
                + f"\n\n_Capacidad libre: {av['remaining_min']} min_"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return
        except ValueError:
            await update.message.reply_text("Formato: /disponibilidad YYYY-MM-DD")
            return

    # Sin argumento: próximos 7 días
    await update.message.reply_text("⏳ Consultando disponibilidad...")
    week = get_week_availability()
    lines = ["📅 *Disponibilidad próximos 7 días*\n"]
    for av in week:
        lines.append(fmt_availability_line(av))
    lines.append("\n_🔩 Compleja  🔧 Standard  ⚡ Rápida_")
    lines.append("_Usa /reservar para pedir cita_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /reservar — ConversationHandler ──────────────────────────────────────────

async def reservar_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    week = get_week_availability()
    # Solo días con al menos un tipo disponible
    available = [av for av in week if any(av.get(t) for t in TIPO_LABELS)]

    if not available:
        await update.message.reply_text(
            "😔 No hay disponibilidad en los próximos 7 días.\n"
            "Contacta directamente con el taller."
        )
        return ConversationHandler.END

    ctx.user_data["available_dates"] = {av["date"]: av for av in available}

    keyboard = [[fmt_availability_line(av)] for av in available]
    keyboard.append(["❌ Cancelar"])

    await update.message.reply_text(
        "🗓 *¿Para qué día quieres la cita?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return ASK_DATE


async def reservar_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Cancelar":
        await update.message.reply_text("Reserva cancelada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Extraer la fecha del texto del botón (formato "lun 10/04")
    # La clave real está en user_data
    chosen_date = None
    for d, av in ctx.user_data["available_dates"].items():
        if fmt_availability_line(av).strip() == text:
            chosen_date = d
            break

    if not chosen_date:
        await update.message.reply_text("Por favor elige una de las fechas del menú.")
        return ASK_DATE

    ctx.user_data["date"] = chosen_date
    av = ctx.user_data["available_dates"][chosen_date]

    # Mostrar solo tipos disponibles ese día
    available_tipos = [
        [f"{label}"] for code, label in TIPO_LABELS.items() if av.get(code)
    ]
    available_tipos.append(["❌ Cancelar"])

    await update.message.reply_text(
        f"✅ *{chosen_date}* seleccionado.\n\n🔧 *¿Qué tipo de reparación necesitas?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(available_tipos, one_time_keyboard=True, resize_keyboard=True),
    )
    return ASK_TIPO


async def reservar_tipo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Cancelar":
        await update.message.reply_text("Reserva cancelada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Mapear label → code
    chosen_code = None
    for code, label in TIPO_LABELS.items():
        if label == text:
            chosen_code = code
            break

    if not chosen_code:
        await update.message.reply_text("Por favor elige una opción del menú.")
        return ASK_TIPO

    ctx.user_data["tipo"] = chosen_code
    await update.message.reply_text(
        "👤 *¿Cómo te llamas?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_NAME


async def reservar_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Por favor escribe tu nombre completo.")
        return ASK_NAME
    ctx.user_data["name"] = name
    await update.message.reply_text("📱 *¿Tu número de teléfono?*", parse_mode="Markdown")
    return ASK_PHONE


async def reservar_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip().replace(" ", "")
    if len(phone) < 9:
        await update.message.reply_text("Por favor escribe un teléfono válido.")
        return ASK_PHONE
    ctx.user_data["phone"] = phone

    d     = ctx.user_data["date"]
    tipo  = TIPO_LABELS[ctx.user_data["tipo"]]
    name  = ctx.user_data["name"]

    keyboard = [["✅ Confirmar reserva"], ["❌ Cancelar"]]
    await update.message.reply_text(
        f"📋 *Resumen de tu cita:*\n\n"
        f"  📅 Fecha: {d}\n"
        f"  🔧 Tipo: {tipo}\n"
        f"  👤 Nombre: {name}\n"
        f"  📱 Teléfono: {phone}\n\n"
        f"_La moto debe estar en el taller a la apertura (10:00h)._",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return CONFIRM


async def reservar_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "✅ Confirmar reserva":
        await update.message.reply_text("Reserva cancelada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text("⏳ Creando tu reserva...", reply_markup=ReplyKeyboardRemove())

    try:
        job = create_booking(
            scheduled_date   = ctx.user_data["date"],
            repair_type_code = ctx.user_data["tipo"],
            customer_name    = ctx.user_data["name"],
            customer_phone   = ctx.user_data["phone"],
        )
        await update.message.reply_text(
            f"✅ *¡Reserva confirmada!*\n\n"
            f"  📋 Nº de cita: #{job['id']}\n"
            f"  📅 Fecha: {job['scheduled_date']}\n"
            f"  🔧 Tipo: {TIPO_LABELS[job['repair_type_code']]}\n\n"
            f"_Recuerda traer la moto a las 10:00h._\n"
            f"_Para cancelar contacta con el taller._",
            parse_mode="Markdown",
        )
        # Notificar al owner
        if OWNER_ID:
            try:
                await ctx.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        f"🔔 *Nueva reserva #{job['id']}*\n\n"
                        f"  📅 {job['scheduled_date']}\n"
                        f"  🔧 {TIPO_LABELS[job['repair_type_code']]}\n"
                        f"  👤 {ctx.user_data.get('name', '—')}\n"
                        f"  📱 {ctx.user_data.get('phone', '—')}"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass  # No interrumpir si falla la notificación
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al crear la reserva: {e}\n"
            "Por favor contacta directamente con el taller."
        )

    ctx.user_data.clear()
    return ConversationHandler.END


async def reservar_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Reserva cancelada.", reply_markup=ReplyKeyboardRemove())
    ctx.user_data.clear()
    return ConversationHandler.END


STATUS_EMOJI = {
    "pending":       "⏳ Pendiente",
    "confirmed":     "✅ Confirmada",
    "in_progress":   "🔄 En progreso",
    "waiting_parts": "⏸️ Esperando piezas",
    "done":          "✔️ Terminada",
    "cancelled":     "❌ Cancelada",
    "no_show":       "👻 No presentado",
    "unschedulable": "⚠️ No planificable",
}


async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("Uso: /estado <número de cita>")
        return
    try:
        job_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("El número de cita debe ser un número entero.")
        return

    try:
        job = get_job(job_id)
    except Exception as e:
        await update.message.reply_text(f"❌ No se encontró la cita #{job_id}.")
        return

    estado = STATUS_EMOJI.get(job["status"], job["status"])
    tipo   = TIPO_LABELS.get(job["repair_type_code"], job["repair_type_code"])
    desc   = job.get("description") or ""
    await update.message.reply_text(
        f"📋 *Cita #{job['id']}*\n\n"
        f"  📅 Fecha: {job['scheduled_date']}\n"
        f"  🔧 Tipo: {tipo}\n"
        f"  Estado: {estado}"
        + (f"\n  📝 {desc[:60]}" if desc else ""),
        parse_mode="Markdown",
    )


def build_reservar_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("reservar", reservar_start)],
        states={
            ASK_DATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reservar_date)],
            ASK_TIPO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reservar_tipo)],
            ASK_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reservar_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reservar_phone)],
            CONFIRM:   [MessageHandler(filters.TEXT & ~filters.COMMAND, reservar_confirm)],
        },
        fallbacks=[CommandHandler("cancelar", reservar_cancel)],
        allow_reentry=True,
    )

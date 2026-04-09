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
    create_booking, get_job, get_jobs_by_phone, cancel_job,
    fmt_availability_line, TIPO_LABELS,
)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Estados de la conversación /reservar
ASK_DATE, ASK_TIPO, ASK_NAME, ASK_PHONE, CONFIRM = range(5)
# Estados de la conversación /cancelar_cita
CANCEL_PHONE, CANCEL_PICK, CANCEL_CONFIRM = range(5, 8)


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

    # Guardar mapa exacto texto_botón → fecha para comparación posterior
    date_map = {}
    keyboard  = []
    for av in available:
        label = fmt_availability_line(av).strip()
        date_map[label] = av["date"]
        keyboard.append([label])
    keyboard.append(["❌ Cancelar"])

    ctx.user_data["date_map"]        = date_map
    ctx.user_data["available_dates"] = {av["date"]: av for av in available}

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

    # Buscar la fecha usando el mapa exacto generado al crear el teclado
    chosen_date = ctx.user_data.get("date_map", {}).get(text)

    if not chosen_date:
        await update.message.reply_text("Por favor elige una de las fechas del menú.")
        return ASK_DATE

    ctx.user_data["date"] = chosen_date
    av = ctx.user_data["available_dates"][chosen_date]

    # Guardar mapa exacto texto_botón → code para tipos
    tipo_map = {}
    available_tipos = []
    for code, label in TIPO_LABELS.items():
        if av.get(code):
            tipo_map[label] = code
            available_tipos.append([label])
    available_tipos.append(["❌ Cancelar"])

    ctx.user_data["tipo_map"] = tipo_map

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

    # Buscar code usando el mapa exacto generado al crear el teclado
    chosen_code = ctx.user_data.get("tipo_map", {}).get(text)

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


# ── /cancelar_cita — ConversationHandler ─────────────────────────────────────

async def cancelar_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text(
        "📱 *¿Cuál es tu número de teléfono?*\n\n"
        "_Lo usaremos para buscar tus citas activas._",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CANCEL_PHONE


async def cancelar_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip().replace(" ", "")
    if len(phone) < 9:
        await update.message.reply_text("Por favor escribe un teléfono válido.")
        return CANCEL_PHONE

    try:
        jobs = get_jobs_by_phone(phone)
    except Exception:
        await update.message.reply_text("❌ Error consultando citas. Inténtalo de nuevo.")
        return CANCEL_PHONE

    if not jobs:
        await update.message.reply_text(
            "😔 No encontramos citas activas para ese teléfono.\n"
            "_Si crees que es un error, contacta con el taller._",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Guardar mapa botón → job_id
    job_map = {}
    keyboard = []
    for j in jobs:
        tipo  = TIPO_LABELS.get(j["repair_type_code"], j["repair_type_code"])
        label = f"#{j['id']} · {j['scheduled_date']} · {tipo}"
        job_map[label] = j["id"]
        keyboard.append([label])
    keyboard.append(["❌ Salir"])

    ctx.user_data["job_map"] = job_map

    await update.message.reply_text(
        f"📋 *Tus citas activas:*\n\n_Elige la que quieres cancelar:_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return CANCEL_PICK


async def cancelar_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Salir":
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    job_id = ctx.user_data.get("job_map", {}).get(text)
    if not job_id:
        await update.message.reply_text("Por favor elige una opción del menú.")
        return CANCEL_PICK

    ctx.user_data["cancel_job_id"]    = job_id
    ctx.user_data["cancel_job_label"] = text

    keyboard = [["✅ Sí, cancelar"], ["❌ No, mantener"]]
    await update.message.reply_text(
        f"⚠️ *¿Confirmas la cancelación?*\n\n_{text}_\n\n"
        f"_Esta acción no se puede deshacer._",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return CANCEL_CONFIRM


async def cancelar_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "✅ Sí, cancelar":
        await update.message.reply_text(
            "Cancelación abortada. Tu cita sigue activa.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    job_id = ctx.user_data["cancel_job_id"]
    try:
        cancel_job(job_id)
        await update.message.reply_text(
            f"✅ *Cita #{job_id} cancelada.*\n\n"
            f"_Si necesitas una nueva cita usa /reservar._",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        if OWNER_ID:
            try:
                await ctx.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"🔔 *Cita #{job_id} cancelada por el cliente.*\n_{ctx.user_data['cancel_job_label']}_",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al cancelar: {e}\nContacta directamente con el taller.",
            reply_markup=ReplyKeyboardRemove(),
        )

    ctx.user_data.clear()
    return ConversationHandler.END


async def cancelar_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    ctx.user_data.clear()
    return ConversationHandler.END


def build_cancelar_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("cancelar_cita", cancelar_start)],
        states={
            CANCEL_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, cancelar_phone)],
            CANCEL_PICK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, cancelar_pick)],
            CANCEL_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancelar_confirm)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_exit)],
        allow_reentry=True,
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

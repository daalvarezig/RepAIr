"""Comandos comunes: /start, /help"""
import os
from telegram import Update
from telegram.ext import ContextTypes

OWNER_ID = int(os.getenv("OWNER_ID", "0"))


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    is_owner = update.effective_user.id == OWNER_ID
    if is_owner:
        msg = (
            "👋 *Hola! Soy el asistente de RepAIr.*\n\n"
            "🔑 *Comandos de gestión:*\n"
            "  /plan — Plan del día por mecánico\n"
            "  /citas — Lista de trabajos del día\n"
            "  /reoptimizar — Regenerar plan\n\n"
            "📅 *Reservas:*\n"
            "  /disponibilidad — Ver huecos libres\n"
            "  /reservar — Crear nueva cita"
        )
    else:
        msg = (
            "👋 *Bienvenido al taller RepAIr*\n\n"
            "Puedo ayudarte a gestionar tu cita:\n\n"
            "  📅 /disponibilidad — Ver días disponibles\n"
            "  🔧 /reservar — Pedir cita\n\n"
            "_La moto debe estar en el taller a las 10:00h del día de la cita._"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)

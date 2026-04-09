"""
RepAIr Bot — Telegram
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from telegram.ext import ApplicationBuilder, CommandHandler
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from handlers.common import cmd_start, cmd_help
from handlers.owner  import cmd_plan, cmd_reoptimizar, cmd_citas
from handlers.client import cmd_disponibilidad, cmd_estado, build_reservar_handler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN no configurado en .env")


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("help",           cmd_help))
    app.add_handler(CommandHandler("disponibilidad", cmd_disponibilidad))
    app.add_handler(CommandHandler("estado",         cmd_estado))
    app.add_handler(CommandHandler("plan",           cmd_plan))
    app.add_handler(CommandHandler("citas",          cmd_citas))
    app.add_handler(CommandHandler("reoptimizar",    cmd_reoptimizar))
    app.add_handler(build_reservar_handler())

    logging.info("RepAIr Bot arrancando...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

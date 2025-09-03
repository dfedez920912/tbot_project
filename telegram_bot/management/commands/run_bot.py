from django.core.management.base import BaseCommand
from django.conf import settings
import os
import signal
import sys
import threading
import time
from pathlib import Path
import json
import logging

# ← Importar run_bot_sync desde handlers.py
from telegram_bot.handlers import run_bot_sync
# ← Importar update_status desde views.py
from web_interface.views import update_status
from web_interface.utils import log_event

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Inicia el bot de Telegram y maneja sesiones'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_event = None
        self.status_file = Path(settings.BASE_DIR) / 'telegram_bot' / 'services_status.json'

    def handle(self, *args, **options):
        # ← Obtener el token del bot
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            self.stderr.write(self.style.ERROR('Falta el token del bot en .env'))
            log_event('ERROR', "Falta el token del bot en .env", 'telegram_bot')
            return

        # ← Crear evento para detener el bot
        self.stop_event = threading.Event()

        # ← Asegurar que el archivo de estado exista
        if not self.status_file.exists():
            try:
                self.status_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.status_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "telegram_running": False,
                        "telegram_start_time": None,
                        "telegram_auto_start": False
                    }, f, ensure_ascii=False, indent=4)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error al crear services_status.json: {e}'))
                log_event('ERROR', f'Error al crear services_status.json: {e}', 'telegram_bot')

        # ← Leer estado actual para mantener auto_start
        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error al leer services_status.json: {e}'))
            log_event('ERROR', f'Error al leer services_status.json: {e}', 'telegram_bot')
            status = {"telegram_auto_start": False}

        # ← Actualizar estado a "corriendo"
        try:
            current_time = time.time()
            update_status(
                telegram_running=True,
                telegram_start_time=current_time,
                telegram_auto_start=status.get("telegram_auto_start", False)
            )
            self.stdout.write(self.style.SUCCESS('Estado del bot actualizado a "corriendo"'))
            log_event('INFO', 'Bot de Telegram iniciado via run_bot.', 'telegram_bot')
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'No se pudo actualizar el estado al iniciar: {e}'))
            log_event('WARNING', f'No se pudo actualizar el estado al iniciar: {e}', 'telegram_bot')

        # ← Manejar señales de interrupción (Ctrl+C)
        def signal_handler(signum, frame):
            self.stdout.write('\n' + self.style.WARNING('Señal de interrupción recibida. Deteniendo el bot...'))
            log_event('INFO', 'Señal de interrupción recibida. Deteniendo el bot...', 'telegram_bot')
            self.stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # ← Iniciar el bot
        try:
            run_bot_sync(token, stop_event=self.stop_event)
        except Exception as e:
            log_event('CRITICAL', f'Error crítico en run_bot: {str(e)}', 'telegram_bot')
            self.stderr.write(self.style.ERROR(f'Error al ejecutar run_bot: {e}'))
        finally:
            # ← Asegurar que el estado se actualice al salir
            try:
                update_status(
                    telegram_running=False,
                    telegram_start_time=None,
                    telegram_auto_start=status.get("telegram_auto_start", False)
                )
                self.stdout.write(self.style.SUCCESS('Estado del bot actualizado a "detenido"'))
                log_event('INFO', 'Bot de Telegram detenido via run_bot.', 'telegram_bot')
            except Exception as e:
                self.stderr.write(self.style.WARNING(f'No se pudo actualizar el estado al detener: {e}'))
                log_event('WARNING', f'No se pudo actualizar el estado al detener: {e}', 'telegram_bot')
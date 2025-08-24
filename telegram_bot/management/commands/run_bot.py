from django.core.management.base import BaseCommand
from django.conf import settings
import os
import signal
import sys
import threading  # ← ¡Importación faltante!
import time
from web_interface.utils import log_event
from telegram_bot.handlers import run_bot_sync

class Command(BaseCommand):
    help = 'Inicia el bot de Telegram y maneja sesiones'

    def handle(self, *args, **options):
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            self.stderr.write(self.style.ERROR('Falta el token del bot en .env'))
            log_event('ERROR', "Falta el token del bot en .env", 'telegram_bot')
            return

        print('🚀 Iniciando bot de Telegram...')
        log_event('INFO', "🚀 Iniciando bot de Telegram...", 'telegram_bot')

        stop_event = threading.Event()

        def signal_handler(signum, frame):
            print('🛑 Señal recibida. Deteniendo el bot...')
            log_event('INFO', "Detención forzada del bot por señal.", 'telegram_bot')
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # ← Ejecutar el bot y bloquear el hilo principal
            run_bot_sync(token, stop_event)
        except Exception as e:
            log_event('CRITICAL', f'Error crítico en run_bot: {str(e)}', 'telegram_bot')
            self.stderr.write(self.style.ERROR(f'Error del bot: {str(e)}'))
        finally:
            print('✅ Bot de Telegram finalizado.')
            log_event('INFO', "Bot de Telegram finalizado.", 'telegram_bot')
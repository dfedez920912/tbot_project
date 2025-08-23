from django.core.management.base import BaseCommand
from django.conf import settings
import os
from web_interface.utils import log_event
from telegram_bot.handlers import run_bot  # ← Importar desde la nueva ubicación

class Command(BaseCommand):
    help = 'Inicia el bot de Telegram y maneja sesiones'

    def handle(self, *args, **options):
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            self.stderr.write(self.style.ERROR('Falta el token del bot en .env'))
            log_event('ERROR',"Falta el token del bot en .env",'telegram_bot')
            return

        self.stdout.write(self.style.SUCCESS('🚀 Iniciando bot de Telegram...'))
        log_event('INFO',"🚀 Iniciando bot de Telegram...",'telegram_bot')
        try:
            run_bot(token)
        except Exception as e:
            log_event('CRITICAL', f'Error crítico en run_bot: {str(e)}', 'telegram_bot')
            self.stderr.write(self.style.ERROR(f'Error del bot: {str(e)}'))
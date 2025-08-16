from django.core.management.base import BaseCommand
from django.conf import settings
import os
from bot_handler.bot_handler import run_bot


class Command(BaseCommand):
    help = 'Inicia el bot de Telegram y maneja sesiones'

    def handle(self, *args, **options):
        token = os.getenv('TELEGRAM_BOT_TOKEN')

        if not token:
            self.stderr.write(self.style.ERROR('Falta el token del bot en .env'))
            return

        self.stdout.write(self.style.SUCCESS('🚀 Iniciando bot de Telegram...'))
        try:
            run_bot(token)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error del bot: {str(e)}'))
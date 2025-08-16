# telegram_bot/management/commands/sync_ussers.py
from django.core.management.base import BaseCommand
from ad_connector.ad_operations import fetch_ad_users
from db_handler.db_handler import refresh_users
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sincronización completa de usuarios desde AD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Muestra toda la traza de ejecución'
        )

    def handle(self, *args, **options):
        # Configurar nivel de logging
        if options['debug']:
            logging.basicConfig(level=logging.DEBUG)

        self.stdout.write("== Iniciando sincronización ==")

        try:
            # Paso 1: Mostrar configuración cargada
            self._display_config()

            # Paso 2: Obtener usuarios de AD
            self.stdout.write("\nConectando a Active Directory...")
            ad_users = fetch_ad_users()

            if not ad_users:
                self.stdout.write(self.style.WARNING("\nResultado de búsqueda: 0 usuarios encontrados"))
                self._suggest_solutions()
                return

            # Paso 3: Mostrar detalles de usuarios encontrados
            self.stdout.write(f"\nUsuarios encontrados ({len(ad_users)}):")
            for idx, user in enumerate(ad_users[:5], 1):
                self.stdout.write(f"{idx}. {user['username']} - {user['name']}")
            if len(ad_users) > 5:
                self.stdout.write(f"... y {len(ad_users) - 5} más")

            # Paso 4: Sincronizar con base de datos
            self.stdout.write("\nIniciando sincronización con la base de datos...")
            count = refresh_users(ad_users)

            # Paso 5: Resultado final
            self.stdout.write(
                self.style.SUCCESS(f"\nSincronización exitosa: {count} usuarios actualizados")
            )

        except Exception as e:
            logger.exception("Error crítico:")
            self.stdout.write(self.style.ERROR(f"\nError: {str(e)}"))
            self.stdout.write("Revise los logs para más detalles")

    def _display_config(self):
        """Muestra la configuración cargada desde .env"""
        from django.conf import settings
        self.stdout.write("\nConfiguración actual:")
        self.stdout.write(f"AD_SERVER: {settings.AD_CONFIG.get('SERVER')}")
        self.stdout.write(f"AD_PORT: {settings.AD_CONFIG.get('PORT')}")
        self.stdout.write(f"AD_SEARCH_BASE: {settings.AD_CONFIG.get('SEARCH_BASE')}")
        self.stdout.write(f"DB_NAME: {settings.DATABASES['default']['NAME']}")

    def _suggest_solutions(self):
        """Muestra sugerencias para resolver problemas comunes"""
        self.stdout.write("\nPosibles soluciones:")
        self.stdout.write("1. Verifique la conexión al servidor AD")
        self.stdout.write("2. Valide los permisos del usuario de AD")
        self.stdout.write("3. Revise el filtro de búsqueda en ad_operations.py")
        self.stdout.write("4. Ejecute con --debug para ver detalles técnicos")
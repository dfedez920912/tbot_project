from django.db import DatabaseError, transaction
from telegram_bot.models import Usuario, Session
from asgiref.sync import sync_to_async
from web_interface.utils import log_event
import logging


def save_user_activity(user_id, action: str):
    try:
        # ... guardar en DB
        log_event(
            level='INFO',
            message=f"Actividad guardada para usuario {user_id}: {action}",
            source='db_handler'
        )
    except Exception as e:
        log_event(
            level='ERROR',
            message=f"Error al guardar actividad de {user_id}: {str(e)}",
            source='db_handler'
        )

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

@transaction.atomic
def refresh_users(users_data):
    """
    Elimina todos los registros actuales y crea nuevos a partir de users_data.
    """
    # Eliminar todos los registros existentes
    Usuario.objects.all().delete()

    # Crear objetos en lote
    users = [
        Usuario(
            username=data['username'],
            name=data['name'],
            mail=data['email'],
            telephonenumber=data['phone']
        ) for data in users_data
    ]

    Usuario.objects.bulk_create(users, batch_size=1000)
    return len(users)

@sync_to_async
def get_user_by_phone(phone_number):
    """Busca un usuario por número de teléfono y devuelve un diccionario con 'name' y 'mail'."""
    try:
        return Usuario.objects.filter(
            telephonenumber=phone_number
        ).values('name', 'mail').first()
    except DatabaseError as e:
        print(f"Error de base de datos: {str(e)}")
        return None

@sync_to_async
def delete_session(session_id: str) -> int:
    """
    Elimina la sesión del usuario identificada por session_id de la tabla Session.
    Devuelve el número de registros eliminados.
    """
    try:
        deleted_count, _ = Session.objects.filter(session_id=session_id).delete()
        return deleted_count
    except DatabaseError as e:
        logger.error(f"Error eliminando sesión: {str(e)}")
        return 0


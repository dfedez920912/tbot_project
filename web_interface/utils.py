import logging
from datetime import datetime
from pathlib import Path
import os
from dotenv import load_dotenv, set_key, get_key


logger = logging.getLogger(__name__)

# Asegúrate de que el directorio logs/ exista
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

os.makedirs(LOG_DIR, exist_ok=True)

# Configurar logging a archivo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(source)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # También muestra en consola
    ]
)

def log_event(level: str, message: str, source: str):
    """
    Registra un evento en archivo y en la base de datos.

    Args:
        level (str): Nivel del log ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
        message (str): Mensaje descriptivo
        source (str): Módulo origen ('bot_handler', 'email_service', etc.)
    """
    # 1. Log en archivo y consola
    extra = {'source': source}
    if level == 'INFO':
        logger.info(message, extra=extra)
    elif level == 'WARNING':
        logger.warning(message, extra=extra)
    elif level == 'ERROR':
        logger.error(message, extra=extra)
    elif level == 'CRITICAL':
        logger.critical(message, extra=extra)

    # 2. Log en base de datos (solo si Django está listo)
    try:
        # ← Importación diferida (evita el ciclo)
        from web_interface.models import LogEntry
        LogEntry.objects.create(
            level=level,
            message=message,
            source=source
        )
    except Exception as e:
        # ← Mostrar el error real
        logger.error(f"[DB] No se pudo guardar log: {e}", extra={'source': 'log_system'})
        


def set_key_in_env(key, value):
    """
    Guarda una clave-valor en el archivo .env
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    # Asegurarse de que el archivo exista
    if not os.path.exists(env_path):
        open(env_path, 'a').close()
    # Escribir la clave
    success, key = set_key(env_path, key, value)
    # Forzar recarga
    load_dotenv(env_path, override=True)
    return success
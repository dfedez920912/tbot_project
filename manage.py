#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import logging.config

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tbot_project.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

# Ruta absoluta a la carpeta "logs" en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')


# Crear la carpeta logs si no existe
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = os.path.join(LOG_DIR, 'project.log')

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,  # Mantiene logger existentes (o puedes poner True si quieres reiniciar)
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },
    'handlers': {
        # Manejador para escribir en el fichero
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': LOG_FILE,
            'formatter': 'standard',
            'encoding': 'utf8',
        },
        # Si no deseas ningún mensaje en consola, no incluyas un handler de tipo StreamHandler
        # O, alternativamente, puedes definirlo pero no asignarlo a la raíz
    },
    'root': {
        'handlers': ['file'],  # Solo se usa el handler de fichero
        'level': 'INFO',
    },
    # Opcional: configura algunos loggers específicos de otras librerías si lo deseas
    'loggers': {
        'telegram': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)


if __name__ == '__main__':
    main()

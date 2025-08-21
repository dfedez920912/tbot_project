from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from ad_connector.ad_operations import authenticate_user, is_ad_admin_group_enabled
from web_interface.utils import log_event
import logging

logger = logging.getLogger(__name__)
User = get_user_model()  # ← Usa el modelo de usuario configurado en Django

class ADGroupBackend(BaseBackend):
    """
    Backend personalizado para autenticación basada en grupo AD.
    """

    def authenticate(self, request, username=None, password=None):
        if not username or not password:
            return None

        # 1. Verificar si el usuario existe en auth_user
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            logger.warning(f"Intento de login fallido: usuario '{username}' no existe en auth_user.")
            log_event('WARNING', f"Intento de login fallido: usuario '{username}' no existe en auth_user.", 'auth_backend')
            return None

        # 2. Verificar el valor de AD_ADMIN_GROUP_AUTH
        if not is_ad_admin_group_enabled():
            # Modo local: autenticar contra la contraseña en auth_user
            if user.check_password(password):
                logger.info(f"Login exitoso para '{username}' (autenticación local).")
                log_event('INFO', f"Usuario '{username}' inició sesión (autenticación local).", 'auth_backend')
                return user
            else:
                logger.warning(f"Login fallido para '{username}': contraseña incorrecta (modo local).")
                log_event('WARNING', f"Login fallido para '{username}': contraseña incorrecta.", 'auth_backend')
                return None

        # 3. Modo AD: autenticar contra el directorio
        if authenticate_user(username, password):
            # ← Opcional: verificar pertenencia al grupo aquí si es necesario
            logger.info(f"Login exitoso para '{username}' (autenticación AD).")
            log_event('INFO', f"Usuario '{username}' inició sesión (autenticación AD).", 'auth_backend')
            return user
        else:
            logger.warning(f"Login fallido para '{username}': credenciales inválidas en AD.")
            log_event('WARNING', f"Login fallido para '{username}': credenciales inválidas en AD.", 'auth_backend')
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
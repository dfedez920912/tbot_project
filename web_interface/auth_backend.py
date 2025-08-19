from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from ad_connector.ad_operations import authenticate_user, check_group_membership, get_ad_group_config, is_ad_admin_group_enabled
import os

class ADGroupBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        # 1. Autenticar contra AD (función original, sin cambios)
        if not authenticate_user(username, password):
            return None

        # 2. Verificar si la autenticación por grupo está habilitada
        if not is_ad_admin_group_enabled():
            # Si está deshabilitada, permitir login básico sin privilegios
            user, created = User.objects.get_or_create(username=username)
            user.is_staff = False
            user.is_superuser = False
            user.save()
            return user

        # 3. Si está habilitada, verificar pertenencia al grupo
        user_email = f"{username}@{os.getenv('AD_DOMAIN', 'example.com')}"
        try:
            is_admin = check_group_membership(user_email)
        except Exception as e:
            print(f"Error verificando grupo: {e}")
            is_admin = False

        # 4. Crear o actualizar usuario de Django
        user, created = User.objects.get_or_create(username=username)
        user.is_staff = is_admin
        user.is_superuser = is_admin
        user.save()

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None